"""Find every frame's picture between its black bars, and keep its block averages.

A film is letterboxed, and some films change their bars as they go: a scene
in 16:9 inside a 2.39:1 film, credits pillarboxed at 4:3. Every frame's bars
are counted afresh. Rows and columns whose brightest pixel is under BLACK
are bar, counted in from each edge. A dark picture counts as more bar than
it has, so a count is cut at the nearest standard bar within SNAP rows, and
a frame with nothing standard near keeps the cut its last frame had.

Of the picture between the bars cut, the block averages: 16 by 16 blocks,
in grey, of the picture scaled to 256 by 256 as OpenCV's block mean hash
scales it. They are what block mean 0 compares with their median and keeps
a bit of; here every block is kept whole, as the sum of its 256 pixels.

Reading a 4K film takes hours, so the frames are shared out between reader
processes, and a run picks up whatever frames are still missing. Readers
seek to their frames by the pixel hashes already in the database, so an
edition is hashed before it is averaged.
"""

import argparse
import os
import sqlite3
from concurrent.futures import ProcessPoolExecutor
from contextlib import closing
from datetime import datetime

import cv2
import numpy as np
from numpy import ndarray

from movie_edition_comparer.algorithms import hash_md5
from movie_edition_comparer.db import (
    create_database, create_pictures_table, frame_count_hashed, pictures_missing, write_pictures,
)

# Brighter than this, a row or column is picture, not bar.
BLACK = 20

# How far a count may be from a standard bar and still be cut there.
SNAP = 12

# Columns are cut only when both sides agree this closely: a dark picture
# reads as black columns, and the two sides of one seldom agree.
COLUMNS_AGREE = 4

# The flat and 16:9 ratios. The scope ratios, 2.35 to 2.40, lie a few rows
# apart at 2160 rows, so a film's own scope bars are measured instead.
RATIOS = [16 / 9, 1.85, 2.0, 2.2]
PILLARBOX_RATIOS = [4 / 3, 1.66]

# Frames averaged between one commit and the next, for each reader.
BATCH_SIZE = 2_000

# Every this many frames, a reader checks that it is where it thinks it is.
CHECK_EVERY = 1_000


def bars_counted(grey: ndarray) -> tuple[int, int, int, int]:
    """Rows of black at the top and bottom, and columns at the left and right."""
    def count(brightest):
        lit = np.flatnonzero(brightest > BLACK)
        return (int(lit[0]), int(len(brightest) - 1 - lit[-1])) if len(lit) else (len(brightest), 0)
    top, bottom = count(grey.max(axis=1))
    left, right = count(grey.max(axis=0))
    return top, bottom, left, right


def _nearest(counted: int, standards: list[int], within: int) -> int | None:
    best = min(standards, key=lambda standard: abs(standard - counted))
    return best if abs(best - counted) <= within else None


class Letterbox:
    """The bars a film of this size can have, and how a frame's count is cut."""

    def __init__(self, width: int, height: int, film_top: int, film_bottom: int):
        self.height = height
        self.default = (film_top, film_bottom, 0, 0)
        def rows(film):
            return sorted({max(0, round((height - width / ratio) / 2)) for ratio in RATIOS} | {film})
        self.top_rows, self.bottom_rows = rows(film_top), rows(film_bottom)
        self.columns = sorted({max(0, round((width - height * ratio) / 2)) for ratio in PILLARBOX_RATIOS}) + [0]

    def cut(self, counted: tuple[int, int, int, int],
            previous: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
        """Where to cut a frame with these bars counted, the last frame having been cut at previous."""
        top_counted, bottom_counted, left_counted, right_counted = counted
        top = _nearest(top_counted, self.top_rows, SNAP)
        bottom = _nearest(bottom_counted, self.bottom_rows, SNAP)
        if top is None or bottom is None or top + bottom >= self.height * 0.6:
            return previous
        columns = 0
        if abs(left_counted - right_counted) <= COLUMNS_AGREE:
            columns = _nearest(left_counted, self.columns, COLUMNS_AGREE) or 0
        return top, bottom, columns, columns


def film_bars(cap, samples: int = 60) -> tuple[int, int]:
    """The film's own letterbox: the commonest count of black rows at the top
    and at the bottom, over lit frames spread through it. They need not be
    equal, since an odd number of rows of bar cannot be split evenly."""
    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    tops, bottoms = [], []
    for k in range(samples):
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(frame_count * (k + 0.5) / samples))
        ok, frame = cap.read()
        if not ok:
            continue
        grey = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        if grey.mean() < 15:
            continue
        top, bottom, _, _ = bars_counted(grey)
        height = grey.shape[0]
        if 0 < top < height // 4:
            tops.append(top)
        if 0 < bottom < height // 4:
            bottoms.append(bottom)
    mode = lambda counts: max(set(counts), key=counts.count) if counts else 0
    return mode(tops), mode(bottoms)


def block_averages(picture: ndarray) -> bytes:
    """The picture's 16x16 block sums, in grey, as 256 little-endian uint16s."""
    small = cv2.resize(picture, (256, 256), interpolation=cv2.INTER_LINEAR_EXACT)
    grey = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
    sums = grey.reshape(16, 16, 16, 16).sum(axis=(1, 3), dtype=np.uint32)
    return sums.astype("<u2").tobytes()


def averages_of(blob: bytes) -> ndarray:
    """Block averages kept by block_averages, back as 256 grey levels."""
    return np.frombuffer(blob, dtype="<u2").astype(np.float32) / 256


def picture_of(frame: ndarray, cut: tuple[int, int, int, int]) -> ndarray:
    top, bottom, left, right = cut
    return frame[top:frame.shape[0] - bottom, left:frame.shape[1] - right]


def average_frame(frame: ndarray, previous: tuple[int, int, int, int],
                  letterbox: Letterbox) -> tuple[tuple, tuple[int, int, int, int], bytes]:
    """A frame's bars counted, where it is cut, and its block averages."""
    counted = bars_counted(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY))
    cut = letterbox.cut(counted, previous)
    return counted, cut, block_averages(picture_of(frame, cut))


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

    Each stretch is sought to, and its first frame is cut as the film is cut;
    after that each frame is cut knowing the last. Every CHECK_EVERY frames
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
            cut = letterbox.default
            for index in range(start, end):
                ok, frame = cap.read()
                if not ok:
                    break
                if index in md5_at and hash_md5(frame) != md5_at[index]:
                    raise RuntimeError(f"{edition}: frame {index} is not the frame hashed there; "
                                       f"the reader has lost its place")
                counted, cut, averages = average_frame(frame, cut, letterbox)
                rows.append((index, *cut, *counted, averages))
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
    with ProcessPoolExecutor(max_workers=len(shares)) as pool:
        decoder_threads = max(1, (os.cpu_count() or 4) // len(shares))
        done = sum(pool.map(_reader, [(video_path, stretches, db_path, edition, letterbox, decoder_threads)
                                      for stretches in shares]))
    print(f"{done} frames averaged")


# --- command -----------------------------------------------------------------

def configure_parser(parser: argparse.ArgumentParser) -> None:
    parser.add_argument('video', help="Path to the video file")
    parser.add_argument('--edition', required=True, help="Name of the edition, e.g. theatrical")
    parser.add_argument('--db', required=True, help="Path to the film's database, e.g. data/two_towers.db")
    parser.add_argument('--readers', default=max(1, (os.cpu_count() or 4) // 4), type=int,
                        help="Number of processes reading the video at once (default: a quarter of the cores)")


def run(args: argparse.Namespace) -> None:
    start_time = datetime.now()
    average_video_frames_to_db(args.video, args.db, args.edition, args.readers)
    print(f"Took {datetime.now() - start_time}")
