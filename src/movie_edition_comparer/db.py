"""The database a film's editions are hashed into.

One file per film. Every edition's frames go in the one table, told apart by
an edition column, and its chapters likewise.
"""

import os
import sqlite3
from contextlib import closing


def create_database(db_path: str) -> None:
    db_dir = os.path.dirname(db_path)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)
    with closing(sqlite3.connect(db_path)) as connection:
        connection.execute("""
            CREATE TABLE IF NOT EXISTS frame_hashes (
                edition TEXT NOT NULL,
                frame_index INTEGER NOT NULL,
                hash_md5 TEXT NOT NULL,
                hash_block_mean_0 TEXT NOT NULL,
                PRIMARY KEY (edition, frame_index)
            )
        """)
        connection.execute("""
            CREATE INDEX IF NOT EXISTS idx_frame_hashes_hash_md5
            ON frame_hashes (edition, hash_md5)
        """)
        connection.execute("""
            CREATE INDEX IF NOT EXISTS idx_frame_hashes_hash_block_mean_0
            ON frame_hashes (edition, hash_block_mean_0)
        """)
        connection.execute("""
            CREATE TABLE IF NOT EXISTS chapters (
                edition TEXT NOT NULL,
                start_time TEXT NOT NULL,
                title TEXT,
                PRIMARY KEY (edition, start_time)
            )
        """)


def write_frames(connection: sqlite3.Connection, edition: str,
                 frames: list[tuple[int, str, str]]) -> None:
    """Frames of one edition, each as (frame_index, hash_md5, hash_block_mean_0)."""
    connection.executemany(
        "INSERT INTO frame_hashes (edition, frame_index, hash_md5, hash_block_mean_0) "
        "VALUES (?, ?, ?, ?)",
        [(edition, *frame) for frame in frames])


def write_chapters(connection: sqlite3.Connection, edition: str,
                   chapters: list[tuple[str, str]]) -> None:
    """Chapters of one edition, each as (start_time, title)."""
    connection.executemany(
        "INSERT INTO chapters (edition, start_time, title) VALUES (?, ?, ?)",
        [(edition, *chapter) for chapter in chapters])
