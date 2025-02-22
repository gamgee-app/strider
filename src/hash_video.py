import hashlib
import sqlite3
from contextlib import closing
from datetime import datetime

import cv2


def hash_frame(frame, hash_algorithm="md5"):
    hash_func = getattr(hashlib, hash_algorithm)()
    hash_func.update(frame.tobytes())
    return hash_func.hexdigest()


def serialize(uint8_array):
    return ''.join(format(x, '02x') for x in uint8_array.flatten())


hashing_algorithms = {
    'md5': lambda img: hash_frame(img, 'md5'),
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


def hash_video_frames_to_db(video_path, db_path, table_name):
    with closing(sqlite3.connect(db_path)) as connection:
        cap = cv2.VideoCapture(video_path)

        frame_index = 0
        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:  # End of video
                break

            hash_column_names = []
            hash_column_values = []
            for name, func in hashing_algorithms.items():
                hash_column_names.append(get_column_name(name))
                hash_column_values.append(func(frame))

            column_names = f"frame_index, {", ".join(hash_column_names)}"
            column_values = f"{frame_index}, {", ".join(f"'{x}'" for x in hash_column_values)}"
            connection.execute(f"""
                INSERT INTO {table_name} ({column_names})
                VALUES ({column_values})
            """)

            frame_index += 1
            if frame_index % 24 == 0:
                connection.commit()
                print(f"Processed {int(frame_index / 24)} seconds")

        cap.release()
        print(f"Hashed {frame_index} frames and stored in {db_path}")


if __name__ == "__main__":
    input_video_path = input(
        "Enter the path to the video file: ") or "C:\\Users\\obroo\\Lord of the Rings\\The Lord of the Rings The Fellowship of the Ring (2001) Theatrical Remux-2160p HDR.mkv-00.00.00.000-00.00.30.003.mkv"
    input_db_path = input("Enter the path to the SQLite database (default: frame_hashes.db): ") or "frame_hashes.db"
    input_table_name = input("Enter the table name (e.g., film_extended): ") or "film"

    create_database(input_db_path, input_table_name)

    startTime = datetime.now()
    hash_video_frames_to_db(input_video_path, input_db_path, input_table_name)
    print(datetime.now() - startTime)
