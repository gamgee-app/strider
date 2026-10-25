"""Hash every frame of an edition into the film's database.

Hashing a film takes hours, so it picks up where it left off: the frames
already in the database are not read again. Seeking a video is not exact,
so where it left off is found by the frames around it rather than trusted.

Each frame's picture is found between its black bars as it is hashed. The
picture hashes are of that picture, not the bars, and its block averages are
kept too, so that the film is read once for both. The pixel hash is of the
whole frame, as the decoder gives it, since that is what finds a frame again
after seeking.

A PQ HDR video can be hashed a second way in the same pass: each picture
taken to SDR by tone.py's curve, into an edition of its own. The two editions
share their pixel hashes and are committed together, so they resume together.
"""

import argparse
import json
import os
import sqlite3
import subprocess
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import datetime

import cv2
from numpy import ndarray
from progress.bar import Bar

from movie_edition_comparer.algorithms import PICTURE_HASHES, hash_md5
from movie_edition_comparer.db import (
    create_database, landmarks_near, last_frame_hashed, write_chapters, write_frames, write_pictures,
)
from movie_edition_comparer.pictures import Letterbox, cut_frame, letterbox_of, picture_row
from movie_edition_comparer.tone import HDR_TO_SDR

# Frames hashed between one commit and the next.
BATCH_SIZE = 10_000

# Frames read but not yet hashed, for each thread hashing them. Reading does
# not wait for hashing otherwise, and a 4K frame is 25 MB: with the hashing
# behind, a batch's worth of frames would sit in memory.
IN_FLIGHT_PER_WORKER = 4

# How long a commit waits on another run writing to the same database: every
# edition of a film goes in the one file, and they may be hashed at once.
LOCK_TIMEOUT = 600

# How far a seek is allowed to land from where it was asked to, either way.
MAX_SEEK_ERROR = 5


def hash_frame(index: int, frame: ndarray, hashes: dict = PICTURE_HASHES,
               picture: ndarray | None = None) -> tuple:
    """The frame's index, its pixel hash, and the picture hashes asked for,
    in the order the database keeps them; one not asked for is left empty.
    The picture hashes are of the picture given, or the whole frame if none is."""
    picture = frame if picture is None else picture
    return (index, hash_md5(frame),
            *(hashing(picture) if name in hashes else None for name, hashing in PICTURE_HASHES.items()))


def measure_frame(index: int, frame: ndarray, hashes: dict, letterbox: Letterbox | None,
                  averages: bool, tone_map: ndarray | None = None) -> tuple:
    """A frame's hashes, of its picture cut from its bars when there is a
    letterbox to cut it by, and that picture's row when averages are kept;
    then the same again of the picture through the tone map, if one is given."""
    picture = frame if letterbox is None else cut_frame(frame, letterbox)
    def measured(picture):
        return hash_frame(index, frame, hashes, picture), (picture_row(index, picture) if averages else None)
    if tone_map is None:
        return measured(picture), None
    return measured(picture), measured(cv2.LUT(picture, tone_map))


# --- chapters ----------------------------------------------------------------

def _timestamp(seconds: float) -> str:
    """HH:MM:SS.nnnnnnnnn, as Matroska chapter files write it."""
    hours, rest = divmod(seconds, 3600)
    minutes, rest = divmod(rest, 60)
    return f"{int(hours):02d}:{int(minutes):02d}:{rest:012.9f}"


def chapters_of(video_path: str) -> list[tuple[str, str]]:
    """The chapters the video carries, each as (start_time, title)."""
    result = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_chapters", video_path],
        capture_output=True, text=True)
    if result.returncode != 0:
        return []
    return [(_timestamp(float(chapter["start_time"])),
             chapter.get("tags", {}).get("title", ""))
            for chapter in json.loads(result.stdout).get("chapters", [])]


# --- seeking -----------------------------------------------------------------

def seek_error(md5s: list[str | None], seek_to: int,
               landmarks: list[tuple[int, str]],
               max_error: int = MAX_SEEK_ERROR) -> int | None:
    """How far a seek landed from where it was asked to.

    md5s are the hashes of the frames read one after another after seeking
    to seek_to. If the seek landed at seek_to + error, the landmark at frame
    n was read at position n - seek_to - error; the error is the one that
    puts every landmark where its hash was read. None if no error does.
    """
    for error in range(-max_error, max_error + 1):
        positions = [index - seek_to - error for index, _ in landmarks]
        if all(0 <= position < len(md5s) and md5s[position] == md5
               for position, (_, md5) in zip(positions, landmarks)):
            return error
    return None


def _seek_to(cap, target: int, db_path: str, edition: str) -> None:
    """Position the capture so that the next read is the frame at target.

    Seeks to a little before some landmarks that lie before the target and
    reads towards it, hashing as it goes, stopping as far short of it as a
    seek can be off so that nothing past it is read whichever way the seek
    went. Where the landmarks turned up says how far off it went, and the
    shortfall is read. A decoder can give out damaged frames for a while
    after a seek, so the frames just before the target are checked as well
    before the place is trusted.
    """
    for margin in (25, 100, 500, 2000):
        landmarks = [(index, md5)
                     for index, md5 in landmarks_near(db_path, edition, max(0, target - margin))
                     if index < target]
        ask = max(0, landmarks[0][0] - MAX_SEEK_ERROR) if landmarks else 0
        if len(landmarks) < 3 or target - ask <= MAX_SEEK_ERROR:
            continue

        cap.set(cv2.CAP_PROP_POS_FRAMES, ask)
        md5s = _read_hashing(cap, target - ask - MAX_SEEK_ERROR)
        error = seek_error(md5s, ask, landmarks)
        if error is None:
            continue
        md5s += _read_hashing(cap, MAX_SEEK_ERROR - error)

        recovered = [(index, md5)
                     for index, md5 in landmarks_near(db_path, edition, target - 1)
                     if index < target]
        if seek_error(md5s, ask, recovered) == error:
            print(f"Picked up at frame {target} (the seek landed {error:+d} frames off)", flush=True)
            return

    print(f"Could not place frame {target} by seeking; reading from the start", flush=True)
    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
    for _ in range(target):
        cap.read()


def _read_hashing(cap, count: int) -> list[str | None]:
    """The pixel hashes of the next count frames, None where there was none."""
    md5s = []
    for _ in range(count):
        ret, frame = cap.read()
        md5s.append(hash_md5(frame) if ret else None)
    return md5s


# --- hashing -----------------------------------------------------------------

def hash_video_frames_to_db(video_path: str, db_path: str, edition: str, workers: int,
                            hashes: dict = PICTURE_HASHES, averages: bool = True,
                            tone_mapped_edition: str | None = None) -> None:
    with closing(sqlite3.connect(db_path)) as connection:
        last = last_frame_hashed(connection, edition)
        pictured = connection.execute(
            "SELECT COUNT(*) FROM frame_pictures WHERE edition = ?", (edition,)).fetchone()[0]
        if tone_mapped_edition:
            last_mapped = last_frame_hashed(connection, tone_mapped_edition)
            if last_mapped != last:
                raise SystemExit(f"{edition} is hashed to frame {last} and {tone_mapped_edition} to {last_mapped}; "
                                 f"they are hashed together, so they must stand at the same frame")
    resume_from = 0 if last is None else last + 1

    # The film's own letterbox, found from frames sampled through it, on a
    # capture of its own so that the one hashing is not moved.
    sampler = cv2.VideoCapture(video_path)
    letterbox = letterbox_of(sampler)
    sampler.release()
    if letterbox:
        print(f"The film's letterbox is {letterbox.described()}", flush=True)
    if averages:
        if resume_from and pictured < resume_from:
            print(f"{resume_from - pictured} frames already hashed have no block averages; "
                  f"strider average fills them in", flush=True)

    cap = cv2.VideoCapture(video_path)
    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    if resume_from >= frame_count:
        print(f"Already hashed, all {frame_count} frames")
        cap.release()
        return

    if resume_from:
        print(f"Resuming from frame {resume_from} of {frame_count}", flush=True)
        _seek_to(cap, resume_from, db_path, edition)

    # Each hash is one frame's work on one thread; the pool is the parallelism.
    # Left to itself OpenCV spreads each call over every core, and the threads
    # spend more time meeting than hashing.
    cv2.setNumThreads(1)

    with (closing(sqlite3.connect(db_path, timeout=LOCK_TIMEOUT)) as connection,
          ThreadPoolExecutor(max_workers=workers) as executor):

        futures = []
        with Bar('Hashing', max=frame_count - resume_from) as bar:
            for frame_index in range(resume_from, frame_count):
                ret, frame = cap.read()
                if not ret:
                    break

                if len(futures) >= workers * IN_FLIGHT_PER_WORKER:
                    futures[-workers * IN_FLIGHT_PER_WORKER].result()
                futures.append(executor.submit(measure_frame, frame_index, frame, hashes, letterbox, averages,
                                               HDR_TO_SDR if tone_mapped_edition else None))
                if len(futures) == BATCH_SIZE:
                    _commit(connection, edition, tone_mapped_edition, futures)
                    futures = []
                bar.next()

        if futures:
            _commit(connection, edition, tone_mapped_edition, futures)

    cap.release()


def _commit(connection: sqlite3.Connection, edition: str, tone_mapped_edition: str | None, futures) -> None:
    measured = [future.result() for future in futures]
    for name, which in ((edition, 0), (tone_mapped_edition, 1)):
        if name:
            write_frames(connection, name, [m[which][0] for m in measured])
            write_pictures(connection, name, [m[which][1] for m in measured if m[which][1]])
    connection.commit()


# --- HDR ---------------------------------------------------------------------

def transfer_of(video_path: str) -> str | None:
    """The video stream's transfer characteristic as ffprobe names it:
    smpte2084 for PQ HDR, bt709 for most SDR, None when not given."""
    result = subprocess.run(
        ["ffprobe", "-v", "quiet", "-select_streams", "v:0", "-print_format", "json",
         "-show_entries", "stream=color_transfer", video_path],
        capture_output=True, text=True)
    if result.returncode != 0:
        return None
    streams = json.loads(result.stdout or "{}").get("streams", [])
    return streams[0].get("color_transfer") if streams else None


def tone_mapped_edition_for(video_path: str, name: str | None) -> str | None:
    """The edition to hash the tone mapped pictures into: the one asked for,
    if the video is PQ HDR; otherwise none, since an SDR video needs no curve."""
    if name and transfer_of(video_path) != "smpte2084":
        print(f"Not PQ HDR, so {name} is not hashed", flush=True)
        return None
    return name


# --- command -----------------------------------------------------------------

def configure_parser(parser: argparse.ArgumentParser) -> None:
    parser.add_argument('video', help="Path to the video file")
    parser.add_argument('--edition', required=True, help="Name of the edition, e.g. theatrical")
    parser.add_argument('--db', required=True, help="Path to the film's database, e.g. data/two_towers.db")
    parser.add_argument('--threads', default=os.cpu_count() or 4, type=int,
                        help="Number of threads to hash on (default: every core)")
    parser.add_argument('--no-averages', action='store_true',
                        help="Do not keep each frame's block averages "
                             "(strider average can add them later, reading the film again)")
    parser.add_argument('--tone-mapped-edition', metavar="NAME",
                        help="If the video is PQ HDR, also hash each picture taken to SDR by one fixed curve "
                             "into this edition, in the same pass (e.g. theatrical_tonemapped)")
    parser.add_argument('--hashes', default=",".join(PICTURE_HASHES), metavar="NAMES",
                        help="Which picture hashes to compute, comma-separated, of "
                             + ", ".join(PICTURE_HASHES) + " (default: all)")


def run(args: argparse.Namespace) -> None:
    start_time = datetime.now()

    create_database(args.db)

    tone_mapped = tone_mapped_edition_for(args.video, args.tone_mapped_edition)

    chapters = chapters_of(args.video)
    if chapters:
        with closing(sqlite3.connect(args.db, timeout=LOCK_TIMEOUT)) as connection:
            for edition in filter(None, (args.edition, tone_mapped)):
                write_chapters(connection, edition, chapters)
            connection.commit()
        print(f"{len(chapters)} chapters")

    wanted = {name: PICTURE_HASHES[name] for name in args.hashes.split(",")}
    if "block_mean_0" not in wanted:
        raise SystemExit("block_mean_0 is the hash the comparison goes by; every frame must have it")
    hash_video_frames_to_db(args.video, args.db, args.edition, args.threads, wanted,
                            averages=not args.no_averages, tone_mapped_edition=tone_mapped)

    print(f"Took {datetime.now() - start_time}")


def main():
    parser = argparse.ArgumentParser(
        prog='strider hash',
        description='Hash every frame of an edition into the film\'s database')
    configure_parser(parser)
    run(parser.parse_args())


if __name__ == "__main__":
    main()
