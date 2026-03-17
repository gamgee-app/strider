import argparse
import concurrent
import os
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import datetime

import cv2
from numpy import ndarray
from progress.bar import Bar

from movie_edition_comparer.algorithms import HASH_COLUMN, hash_frame
from movie_edition_comparer.db import FRAME_HASHES_TABLE


def create_database(db_path: str):
    db_dir = os.path.dirname(db_path)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)
    with closing(sqlite3.connect(db_path)) as connection:
        connection.execute(
            f"CREATE TABLE IF NOT EXISTS {FRAME_HASHES_TABLE} (\n"
            f"    edition TEXT NOT NULL,\n"
            f"    frame_index INTEGER NOT NULL,\n"
            f"    {HASH_COLUMN} TEXT NOT NULL,\n"
            f"    PRIMARY KEY (edition, frame_index)\n"
            f")"
        )
        connection.execute(
            f"CREATE INDEX IF NOT EXISTS idx_{FRAME_HASHES_TABLE}_{HASH_COLUMN} "
            f"ON {FRAME_HASHES_TABLE} (edition, {HASH_COLUMN})"
        )


def hash_frame_at(index: int, frame: ndarray) -> tuple[int, str]:
    return index, hash_frame(frame)


def hash_video_frames_to_db(video_path: str, db_path: str, edition: str, workers: int):
    cap = cv2.VideoCapture(video_path)

    with (closing(sqlite3.connect(db_path)) as connection,
          ThreadPoolExecutor(max_workers=workers) as executor):

        futures = []
        frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        with Bar('Hashing', max=frame_count) as bar:
            for frame_index in range(frame_count):
                ret, frame = cap.read()
                if not ret:
                    break

                future = executor.submit(hash_frame_at, frame_index, frame)
                futures.append(future)
                bar.next()

        with Bar('Inserting', max=len(futures)) as bar:
            for future in concurrent.futures.as_completed(futures):
                index, frame_hash = future.result()
                connection.execute(
                    f"INSERT INTO {FRAME_HASHES_TABLE} (edition, frame_index, {HASH_COLUMN}) "
                    f"VALUES (?, ?, ?)",
                    (edition, index, frame_hash),
                )
                bar.next()

        connection.commit()

    cap.release()


def configure_parser(parser: argparse.ArgumentParser):
    """Add hash-video arguments to an argument parser."""
    parser.add_argument('video', help="Path to the video file")
    parser.add_argument('--edition', required=True, help="Edition name (e.g. 'theatrical', 'extended')")
    parser.add_argument('--db', default="data/frame_hashes.db", help="Path to database file")
    parser.add_argument('--threads', default=4, type=int, help="Number of threads to use")


def run(args):
    """Run the hash-video command with parsed arguments."""
    start_time = datetime.now()
    create_database(args.db)
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
