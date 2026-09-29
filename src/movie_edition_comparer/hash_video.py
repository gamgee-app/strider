import argparse
import concurrent
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import datetime

import cv2
from numpy import ndarray
from progress.bar import Bar

from movie_edition_comparer.algorithms import hash_block_mean_0, hash_md5
from movie_edition_comparer.db import create_database, write_frames


def hash_frame(index: int, frame: ndarray) -> tuple[int, str, str]:
    return index, hash_md5(frame), hash_block_mean_0(frame)


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

                future = executor.submit(hash_frame, frame_index, frame)
                futures.append(future)
                bar.next()

        with Bar('Inserting', max=len(futures)) as bar:
            for future in concurrent.futures.as_completed(futures):
                write_frames(connection, edition, [future.result()])
                bar.next()

        connection.commit()

    cap.release()


def main():
    parser = argparse.ArgumentParser(
        prog='Hash Video',
        description='Calculates the hashes for each frame of a video, and saves the results to a database'
    )

    parser.add_argument('video', help="Path to the video file")
    parser.add_argument('--edition', required=True, help="Name of the edition, e.g. theatrical")
    parser.add_argument('--db', required=True, help="Path to the film's database, e.g. data/two_towers.db")
    parser.add_argument('--threads', default=4, type=int, help="Number of threads to use")
    args = parser.parse_args()

    start_time = datetime.now()

    create_database(args.db)
    hash_video_frames_to_db(args.video, args.db, args.edition, args.threads)

    print(f"Took {datetime.now() - start_time}")


if __name__ == "__main__":
    main()
