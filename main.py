import cv2
import hashlib
import sqlite3
from datetime import datetime


def hash_frame(frame, hash_algorithm="md5"):
    """
    Compute the hash of a video frame.

    Args:
        frame (numpy.ndarray): The video frame as a NumPy array.
        hash_algorithm (str): Hash algorithm ('md5', 'sha1', 'sha256', etc.).

    Returns:
        str: The computed hash as a hexadecimal string.
    """
    hash_func = getattr(hashlib, hash_algorithm)()
    hash_func.update(frame.tobytes())
    return hash_func.hexdigest()


def create_database(db_path, table_name):
    """
    Create an SQLite database with a table for frame hashes.

    Args:
        db_path (str): Path to the SQLite database file.
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute(f"""
        CREATE TABLE IF NOT EXISTS {table_name} (
            frame_index INTEGER PRIMARY KEY,
            md5_hash TEXT NOT NULL,
            average_hash TEXT NOT NULL,
            perceptual_hash TEXT NOT NULL,
            marr_hildreth_hash TEXT NOT NULL,
            radial_variance_hash TEXT NOT NULL,
            block_mean_hash TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()


def serialize(uint8_array):
    return ''.join(format(x, '02x') for x in uint8_array.flatten())


def hash_video_frames_to_db(video_path, db_path, table_name):
    """
    Hash video frames and store the results in an SQLite database.
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        print(f"Error: Could not open video file {video_path}")
        return

    frame_index = 0
    hashed_frames = 0

    while True:
        ret, frame = cap.read()
        if not ret:  # End of video
            break

        md5_hash = hash_frame(frame)
        average_hash = serialize(cv2.img_hash.averageHash(frame))
        perceptual_hash = serialize(cv2.img_hash.pHash(frame))
        marr_hildreth_hash = serialize(cv2.img_hash.marrHildrethHash(frame))
        radial_variance_hash = serialize(cv2.img_hash.radialVarianceHash(frame))
        block_mean_hash = serialize(cv2.img_hash.blockMeanHash(frame))
        # color_moment_hash = cv2.img_hash.colorMomentHash(frame)

        cursor.execute(f"""
            INSERT INTO {table_name} 
                (frame_index, md5_hash, average_hash, perceptual_hash, marr_hildreth_hash, radial_variance_hash, block_mean_hash)
            VALUES 
                (?, ?, ?, ?, ?, ?, ?)
        """, (frame_index, md5_hash, average_hash, perceptual_hash, marr_hildreth_hash, radial_variance_hash, block_mean_hash))

        hashed_frames += 1

        if frame_index % 24 == 0:
            conn.commit()
            print(f"Processed {int(frame_index / 24)} seconds")

        frame_index += 1

    cap.release()
    conn.close()

    print(f"Hashed {hashed_frames} frames and stored in {db_path}")


if __name__ == "__main__":
    video_path = input("Enter the path to the video file: ")
    db_path = input("Enter the path to the SQLite database (default: frame_hashes.db): ") or "frame_hashes.db"
    table_name = input("Enter the table name (e.g., film_extended): ")

    create_database(db_path, table_name)

    startTime = datetime.now()
    hash_video_frames_to_db(video_path, db_path, table_name)
    print(datetime.now() - startTime)
