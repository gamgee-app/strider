"""Keep the block averages of every frame's picture, for an edition hashed without them.

strider hash keeps them as it hashes, so a film is read once. This reads an
edition again for the frames that have none -- one hashed before they were
kept, or with them turned off -- and keeps them as hashing would have.

Reading a 4K film takes hours, so the frames are shared out between reader
processes, and a run picks up whatever frames are still missing. Readers
seek to their frames by the pixel hashes already in the database, so an
edition is hashed before it is averaged.

A reader holds about a gigabyte: a 4K decoder keeps the frames that a later
frame may be built from, and at this size those are 50 megabytes each. So
readers are counted in gigabytes of memory as much as in cores, and there
are few of them by default.
"""

import argparse
import multiprocessing
import os
import sqlite3
from concurrent.futures import ProcessPoolExecutor
from contextlib import closing
from datetime import datetime

import cv2

from movie_edition_comparer.algorithms import hash_md5
from movie_edition_comparer.db import (
    create_database, create_pictures_table, frame_count_hashed, pictures_missing, write_pictures,
)
from movie_edition_comparer.pictures import Letterbox, film_bars, picture_row

# Frames averaged between one commit and the next, for each reader.
BATCH_SIZE = 2_000

# Every this many frames, a reader checks that it is where it thinks it is.
CHECK_EVERY = 1_000


# --- reading -----------------------------------------------------------------

def share(missing: list[tuple[int, int]], readers: int) -> list[list[tuple[int, int]]]:
    """The missing stretches cut into one share for each reader, as even as a
    stretch's frames allow, each share a run of stretches in frame order."""
    total = sum(end - start for start, end in missing)
    if not total:
        return []
    size = -(-total // readers)
    shares, current, room = [], [], size
    for start, end in missing:
        while start < end:
            take = min(end - start, room)
            current.append((start, start + take))
            start += take
            room -= take
            if room == 0:
                shares.append(current)
                current, room = [], size
    if current:
        shares.append(current)
    return shares


def average_stretches(cap, stretches: list[tuple[int, int]], db_path: str, edition: str,
                      letterbox: Letterbox, seek=None) -> int:
    """Average the frames of these stretches, read from cap, into the database.

    Each stretch is sought to and read on. Every CHECK_EVERY frames
    the frame read is checked against its pixel hash, so that a reader that
    has lost its place stops rather than filing pictures under other frames.
    """
    if seek is None:
        from movie_edition_comparer.hash_video import _seek_to as seek
    with closing(sqlite3.connect(db_path, timeout=600)) as connection:
        md5_at = dict(connection.execute(
            "SELECT frame_index, hash_md5 FROM frame_hashes WHERE edition = ? AND frame_index % ? = 0",
            (edition, CHECK_EVERY)))
        done, rows = 0, []
        for start, end in stretches:
            seek(cap, start, db_path, edition)
            for index in range(start, end):
                ok, frame = cap.read()
                if not ok:
                    break
                if index in md5_at and hash_md5(frame) != md5_at[index]:
                    raise RuntimeError(f"{edition}: frame {index} is not the frame hashed there; "
                                       f"the reader has lost its place")
                rows.append(picture_row(index, frame, letterbox))
                if len(rows) == BATCH_SIZE:
                    write_pictures(connection, edition, rows)
                    connection.commit()
                    done += len(rows)
                    rows = []
                    print(f"{edition}: frame {index} averaged ({done} by this reader)", flush=True)
        if rows:
            write_pictures(connection, edition, rows)
            connection.commit()
            done += len(rows)
    return done


def _reader(args) -> int:
    video_path, stretches, db_path, edition, letterbox, decoder_threads = args
    # Left to itself each reader's decoder starts a thread for every core,
    # and readers together start far more threads than there are cores.
    os.environ.setdefault("OPENCV_FFMPEG_CAPTURE_OPTIONS", f"threads;{decoder_threads}")
    cv2.setNumThreads(1)
    cap = cv2.VideoCapture(video_path)
    try:
        return average_stretches(cap, stretches, db_path, edition, letterbox)
    finally:
        cap.release()


def average_video_frames_to_db(video_path: str, db_path: str, edition: str, readers: int) -> None:
    create_database(db_path)
    with closing(sqlite3.connect(db_path)) as connection:
        connection.execute("PRAGMA journal_mode=WAL")
        create_pictures_table(connection)
        connection.commit()
        frame_count = frame_count_hashed(connection, edition)
        if not frame_count:
            raise SystemExit(f"{edition} is not hashed; hash it first, since averaging finds its place by the hashes")
        missing = pictures_missing(connection, edition, frame_count)
    if not missing:
        print(f"Already averaged, all {frame_count} frames")
        return

    cap = cv2.VideoCapture(video_path)
    width, height = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    film_top, film_bottom = film_bars(cap)
    cap.release()
    print(f"The film's letterbox is {film_top} rows at the top and {film_bottom} at the bottom", flush=True)
    letterbox = Letterbox(width, height, film_top, film_bottom)

    shares = share(missing, readers)
    print(f"{sum(b - a for a, b in missing)} frames to average, shared between {len(shares)} readers", flush=True)
    # Readers start afresh rather than as copies of this process: a copy made
    # after OpenCV has read a video can inherit a lock one of its threads held,
    # and wait on it for ever.
    with ProcessPoolExecutor(max_workers=len(shares), mp_context=multiprocessing.get_context("spawn")) as pool:
        decoder_threads = max(1, (os.cpu_count() or 4) // len(shares))
        done = sum(pool.map(_reader, [(video_path, stretches, db_path, edition, letterbox, decoder_threads)
                                      for stretches in shares]))
    print(f"{done} frames averaged")


# --- command -----------------------------------------------------------------

def configure_parser(parser: argparse.ArgumentParser) -> None:
    parser.add_argument('video', help="Path to the video file")
    parser.add_argument('--edition', required=True, help="Name of the edition, e.g. theatrical")
    parser.add_argument('--db', required=True, help="Path to the film's database, e.g. data/two_towers.db")
    parser.add_argument('--readers', default=max(1, (os.cpu_count() or 4) // 8), type=int,
                        help="Number of processes reading the video at once. Each holds about a gigabyte "
                             "for the decoder, so this is bounded by memory as much as by cores "
                             "(default: an eighth of the cores)")


def run(args: argparse.Namespace) -> None:
    start_time = datetime.now()
    average_video_frames_to_db(args.video, args.db, args.edition, args.readers)
    print(f"Took {datetime.now() - start_time}")
