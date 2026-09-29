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
    """Chapters of one edition, each as (start_time, title).

    Written again, a chapter replaces itself, so hashing an edition a second
    time does not fail on the chapters it wrote the first.
    """
    connection.executemany(
        "INSERT OR REPLACE INTO chapters (edition, start_time, title) VALUES (?, ?, ?)",
        [(edition, *chapter) for chapter in chapters])


def last_frame_hashed(connection: sqlite3.Connection, edition: str) -> int | None:
    """The index of the last frame this edition has, or None if it has none."""
    return connection.execute(
        "SELECT MAX(frame_index) FROM frame_hashes WHERE edition = ?",
        (edition,)).fetchone()[0]


def landmarks_near(db_path: str, edition: str, centre: int,
                   how_many: int = 5) -> list[tuple[int, str]]:
    """Frames about a place that can be told apart by their pixels.

    Seeking a video is not exact, so a frame reached by seeking is placed by
    finding these around it. Frames that repeat -- black, a held frame --
    cannot place anything, so one frame stands for each pixel hash and the
    window widens until enough are in it, or there are no more to be had.
    Given as (frame_index, hash_md5), nearest the centre first taken, in
    frame order.
    """
    with closing(sqlite3.connect(db_path)) as connection:
        window = 20
        while window < 100_000:
            rows = connection.execute("""
                SELECT frame_index, hash_md5
                FROM frame_hashes
                WHERE edition = ? AND frame_index >= ? AND frame_index < ?
                ORDER BY ABS(frame_index - ?)
            """, (edition, max(0, centre - window // 2), centre + window // 2, centre))
            seen: set[str] = set()
            landmarks: list[tuple[int, str]] = []
            for index, md5 in rows:
                if md5 not in seen:
                    seen.add(md5)
                    landmarks.append((index, md5))
                    if len(landmarks) == how_many:
                        return sorted(landmarks)
            window *= 2
        return sorted(landmarks)
