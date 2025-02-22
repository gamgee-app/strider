import argparse
import concurrent
import hashlib
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import datetime
from progress.bar import Bar

import cv2


def get_frame_hash(frame, hash_algorithm="md5"):
    hash_func = getattr(hashlib, hash_algorithm)()
    hash_func.update(frame.tobytes())
    return hash_func.hexdigest()


def serialize(uint8_array):
    return ''.join(format(x, '02x') for x in uint8_array.flatten())


hashing_algorithms = {
    'md5': lambda img: get_frame_hash(img, 'md5'),
    'average': lambda img: serialize(cv2.img_hash.averageHash(img)),
    'perceptual': lambda img: serialize(cv2.img_hash.pHash(img)),
    'marr_hildreth': lambda img: serialize(cv2.img_hash.marrHildrethHash(img)),
    'radial_variance': lambda img: serialize(cv2.img_hash.radialVarianceHash(img)),
    'block_mean': lambda img: serialize(cv2.img_hash.blockMeanHash(img)),
    # 'color_moment': lambda img : serialize(cv2.img_hash.colorMomentHash(img))
}


def get_column_name(algorithm):
    return f"hash_{algorithm}"


def create_database(db_path, table_name):
    hash_columns = [f"{get_column_name(x)} TEXT NOT NULL" for x in hashing_algorithms]
    create_table_query = f"""
        CREATE TABLE IF NOT EXISTS {table_name} (
            frame_index INTEGER PRIMARY KEY,
            {",\n\t\t".join(hash_columns)}
        )
    """

    with closing(sqlite3.connect(db_path)) as connection:
        connection.execute(create_table_query)


def get_frame_hashes(index, frame):
    return index, {name: func(frame) for name, func in hashing_algorithms.items()}


def hash_video_frames_to_db(video_path, db_path, table_name, workers):
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


parser = argparse.ArgumentParser(
    prog='Hash Video',
    description='Calculates the hashes for each frame of a video, and saves the results to a database'
)

parser.add_argument('video', help="Path to the video file")
parser.add_argument('table', help="Name of the table to save data to")
parser.add_argument('--db', default="data/frame_hashes.db", help="Path to database file")
parser.add_argument('--threads', default=4, type=int, help="Number of threads to use")

if __name__ == "__main__":
    startTime = datetime.now()

    args = parser.parse_args()
    create_database(args.db, args.table)
    hash_video_frames_to_db(args.video, args.db, args.table, int(args.threads))

    print(f"Took {datetime.now() - startTime}")
