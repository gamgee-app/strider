import argparse
import concurrent
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

from movie_edition_comparer.algorithms import (
    hash_frame_block_mean_0,
    hash_frame_block_mean_1,
    hash_frame_md5,
)


def create_database(db_path: str):
    db_dir = os.path.dirname(db_path)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)
    with closing(sqlite3.connect(db_path)) as connection:
        connection.execute(
            "CREATE TABLE IF NOT EXISTS frame_hashes ("
            "    edition TEXT NOT NULL,"
            "    frame_index INTEGER NOT NULL,"
            "    hash_md5 TEXT NOT NULL,"
            "    hash_block_mean_0 TEXT NOT NULL,"
            "    hash_block_mean_1 TEXT NOT NULL,"
            "    PRIMARY KEY (edition, frame_index)"
            ")"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_frame_hashes_hash_block_mean_0 "
            "ON frame_hashes (edition, hash_block_mean_0)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_frame_hashes_hash_md5 "
            "ON frame_hashes (edition, hash_md5)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_frame_hashes_hash_block_mean_1 "
            "ON frame_hashes (edition, hash_block_mean_1)"
        )
        connection.execute(
            "CREATE TABLE IF NOT EXISTS chapters ("
            "    edition TEXT NOT NULL,"
            "    start_time TEXT NOT NULL,"
            "    title TEXT,"
            "    PRIMARY KEY (edition, start_time)"
            ")"
        )


def _seconds_to_timestamp(seconds: float) -> str:
    """Convert seconds to HH:MM:SS.nnnnnnnnn format."""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    return f"{h:02d}:{m:02d}:{s:012.9f}"


def extract_chapters(video_path: str) -> list[tuple[str, str]]:
    """Extract chapters from a video file using ffprobe.

    Returns list of (start_time, title) tuples.
    """
    result = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_chapters", video_path],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        return []

    data = json.loads(result.stdout)
    chapters = []
    for ch in data.get("chapters", []):
        start = _seconds_to_timestamp(float(ch["start_time"]))
        title = ch.get("tags", {}).get("title", "")
        chapters.append((start, title))
    return chapters


def save_chapters(chapters: list[tuple[str, str]], db_path: str, edition: str):
    """Save chapters to the database."""
    if not chapters:
        return
    with closing(sqlite3.connect(db_path)) as connection:
        connection.executemany(
            "INSERT OR REPLACE INTO chapters (edition, start_time, title) "
            "VALUES (?, ?, ?)",
            [(edition, start, title) for start, title in chapters],
        )
        connection.commit()
    print(f"  Imported {len(chapters)} chapters")


def hash_frame_at(index: int, frame: ndarray) -> tuple[int, str, str, str]:
    return (
        index,
        hash_frame_md5(frame),
        hash_frame_block_mean_0(frame),
        hash_frame_block_mean_1(frame),
    )


BATCH_SIZE = 10_000
MAX_SEEK_ERROR = 5


def _seek_to_frame(cap, target: int, db_path: str, edition: str):
    """Seek to target frame using MD5 anchoring for position verification.

    After this call, the next cap.read() will return the frame at target.
    Uses progressively larger margins if the decoder hasn't recovered
    from the seek by the time we reach the target.
    """
    from movie_edition_comparer.db import fetch_md5_landmarks

    for margin in [25, 100, 500, 2000]:
        anchor_at = max(0, target - margin)
        landmarks = fetch_md5_landmarks(db_path, edition, anchor_at)
        landmarks = [(idx, md5) for idx, md5 in landmarks if idx < target]
        if len(landmarks) < 3:
            continue

        earliest = min(idx for idx, _ in landmarks)

        # Seek before the earliest landmark, read exactly up to target.
        # For seek error E, cap reads frames [seek_to+E, seek_to+E+buffer_size-1].
        # We want the last frame read to be at most target-1, so:
        #   seek_to + E + buffer_size - 1 <= target - 1 for E = 0
        #   buffer_size = target - seek_to
        # For E < 0 (seek lands before target): cap ends at target+E < target,
        #   we read forward |E| frames to reach target.
        # For E > 0 (seek lands ahead): cap ends at target+E > target,
        #   we've overshot — try next margin.
        seek_to = max(0, earliest - MAX_SEEK_ERROR)
        buffer_size = target - seek_to

        cap.set(cv2.CAP_PROP_POS_FRAMES, seek_to)
        frames_md5 = []
        for _ in range(buffer_size):
            ret, frame = cap.read()
            frames_md5.append(hash_frame_md5(frame) if ret else None)

        # Find the seek error by sliding landmarks across the buffer
        found_error = None
        for error in range(-MAX_SEEK_ERROR, MAX_SEEK_ERROR + 1):
            all_match = True
            for landmark_idx, expected_md5 in landmarks:
                read_pos = landmark_idx - seek_to - error
                if read_pos < 0 or read_pos >= len(frames_md5) or frames_md5[read_pos] is None:
                    all_match = False
                    break
                if frames_md5[read_pos] != expected_md5:
                    all_match = False
                    break
            if all_match:
                found_error = error
                break

        if found_error is None:
            continue

        if found_error > 0:
            # Overshot target — try next margin
            continue

        # Read forward to reach target (for error <= 0)
        remaining = -found_error
        for _ in range(remaining):
            cap.read()

        # Verify the decoder has recovered by checking landmarks near target
        verify_landmarks = fetch_md5_landmarks(db_path, edition, target - 1)
        verify_landmarks = [(idx, md5) for idx, md5 in verify_landmarks if idx < target]
        all_verified = True
        for v_idx, v_md5 in verify_landmarks:
            buf_pos = v_idx - seek_to - found_error
            if buf_pos < 0 or buf_pos >= len(frames_md5) or frames_md5[buf_pos] != v_md5:
                all_verified = False
                break

        if all_verified:
            print(f"  Anchored at frame {target} (seek_error={found_error}, margin={margin})")
            return

        # Decoder artifacts — try a larger margin
        continue

    # All margins failed — sequential read from start
    print(f"  Could not anchor, reading sequentially from frame 0...")
    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
    for _ in range(target):
        cap.read()


def hash_video_frames_to_db(video_path: str, db_path: str, edition: str, workers: int):
    with closing(sqlite3.connect(db_path)) as connection:
        row = connection.execute(
            "SELECT MAX(frame_index) FROM frame_hashes WHERE edition = ?",
            (edition,),
        ).fetchone()
        resume_from = (row[0] + 1) if row[0] is not None else 0

    cap = cv2.VideoCapture(video_path)
    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    if resume_from >= frame_count:
        print(f"Already complete ({resume_from} frames)")
        cap.release()
        return

    if resume_from > 0:
        print(f"Resuming from frame {resume_from}...")
        _seek_to_frame(cap, resume_from, db_path, edition)

    with (closing(sqlite3.connect(db_path)) as connection,
          ThreadPoolExecutor(max_workers=workers) as executor):

        futures = []
        remaining = frame_count - resume_from
        with Bar("Hashing", max=remaining) as bar:
            for frame_index in range(resume_from, frame_count):
                ret, frame = cap.read()
                if not ret:
                    break

                future = executor.submit(hash_frame_at, frame_index, frame)
                futures.append(future)

                if len(futures) >= BATCH_SIZE:
                    _commit_batch(connection, futures, edition)
                    futures = []

                bar.next()

        if futures:
            _commit_batch(connection, futures, edition)

    cap.release()


def _commit_batch(connection, futures, edition):
    for future in concurrent.futures.as_completed(futures):
        index, md5, bm0, bm1 = future.result()
        connection.execute(
            "INSERT INTO frame_hashes "
            "(edition, frame_index, hash_md5, hash_block_mean_0, hash_block_mean_1) "
            "VALUES (?, ?, ?, ?, ?)",
            (edition, index, md5, bm0, bm1),
        )
    connection.commit()


def configure_parser(parser: argparse.ArgumentParser):
    """Add hash-video arguments to an argument parser."""
    parser.add_argument('video', help="Path to the video file")
    parser.add_argument('--edition', required=True, help="Edition name (e.g. 'theatrical', 'extended')")
    parser.add_argument('--db', required=True, help="Path to movie database file (e.g. 'data/two_towers.db')")
    parser.add_argument('--threads', default=os.cpu_count() or 4, type=int, help="Number of threads to use")


def run(args):
    """Run the hash-video command with parsed arguments."""
    start_time = datetime.now()
    create_database(args.db)

    chapters = extract_chapters(args.video)
    save_chapters(chapters, args.db, args.edition)

    hash_video_frames_to_db(args.video, args.db, args.edition, args.threads)
    print(f"Took {datetime.now() - start_time}")


def main():
    parser = argparse.ArgumentParser(
        prog='Hash Video',
        description='Calculates the hashes for each frame of a video, and saves the results to a database'
    )
    configure_parser(parser)
    args = parser.parse_args()
    run(args)


if __name__ == "__main__":
    main()
