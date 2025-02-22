import argparse
import concurrent
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import datetime

import cv2
from numpy import ndarray
from progress.bar import Bar

from algorithms import hashing_algorithms, get_column_name


def create_database(db_path: str, table_name: str):
    hash_columns = [f"{get_column_name(x)} TEXT NOT NULL" for x in hashing_algorithms]
    create_table_query = f"""
        CREATE TABLE IF NOT EXISTS {table_name} (
            frame_index INTEGER PRIMARY KEY,
            {",\n\t\t".join(hash_columns)}
        )
    """

    with closing(sqlite3.connect(db_path)) as connection:
        connection.execute(create_table_query)


def get_frame_hashes(index: int, frame: ndarray):
    return index, {name: func(frame) for name, func in hashing_algorithms.items()}


def hash_video_frames_to_db(video_path: str, db_path: str, table_name: str, workers: int):
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

                future = executor.submit(get_frame_hashes, frame_index, frame)
                futures.append(future)
                bar.next()

        with Bar('Inserting', max=len(futures)) as bar:
            for future in concurrent.futures.as_completed(futures):
                index, hashes = future.result()
                values = [index] + list(hashes.values())

                column_names = f"frame_index, {", ".join(get_column_name(x) for x in hashes.keys())}"
                values_names = ", ".join(["?" for _ in values])

                connection.execute(f"""
                    INSERT INTO {table_name} ({column_names})
                    VALUES ({values_names})
                """, values)
                bar.next()

        connection.commit()

    cap.release()


def main():
    parser = argparse.ArgumentParser(
        prog='Hash Video',
        description='Calculates the hashes for each frame of a video, and saves the results to a database'
    )

    parser.add_argument('video', help="Path to the video file")
    parser.add_argument('table', help="Name of the table to save data to")
    parser.add_argument('--db', default="data/frame_hashes.db", help="Path to database file")
    parser.add_argument('--threads', default=4, type=int, help="Number of threads to use")
    args = parser.parse_args()

    start_time = datetime.now()

    create_database(args.db, args.table)
    hash_video_frames_to_db(args.video, args.db, args.table, args.threads)

    print(f"Took {datetime.now() - start_time}")


if __name__ == "__main__":
    main()
