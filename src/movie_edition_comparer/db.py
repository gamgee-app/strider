"""The database a film's editions are hashed into.

One file per film. Every edition's frames go in the one table, told apart by
an edition column, and its chapters likewise.
"""

import os
import sqlite3
from contextlib import closing

from movie_edition_comparer.algorithms import PICTURE_HASHES


# The picture hashes, as columns, in the order write_frames takes them. The
# first is the one the comparison goes by, and the only one a frame must have.
PICTURE_COLUMNS = [f"hash_{name}" for name in PICTURE_HASHES]


def create_database(db_path: str) -> None:
    db_dir = os.path.dirname(db_path)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)
    with closing(sqlite3.connect(db_path)) as connection:
        connection.execute(f"""
            CREATE TABLE IF NOT EXISTS frame_hashes (
                edition TEXT NOT NULL,
                frame_index INTEGER NOT NULL,
                hash_md5 TEXT NOT NULL,
                {PICTURE_COLUMNS[0]} TEXT NOT NULL,
                {", ".join(f"{column} TEXT" for column in PICTURE_COLUMNS[1:])},
                PRIMARY KEY (edition, frame_index)
            )
        """)
        # A database from before a hash was added gets its column, empty.
        present = {row[1] for row in connection.execute("PRAGMA table_info(frame_hashes)")}
        for column in PICTURE_COLUMNS:
            if column not in present:
                connection.execute(f"ALTER TABLE frame_hashes ADD COLUMN {column} TEXT")
        connection.execute("""
            CREATE INDEX IF NOT EXISTS idx_frame_hashes_hash_md5
            ON frame_hashes (edition, hash_md5)
        """)
        connection.execute(f"""
            CREATE INDEX IF NOT EXISTS idx_frame_hashes_{PICTURE_COLUMNS[0]}
            ON frame_hashes (edition, {PICTURE_COLUMNS[0]})
        """)
        create_pictures_table(connection)
        connection.execute("""
            CREATE TABLE IF NOT EXISTS chapters (
                edition TEXT NOT NULL,
                start_time TEXT NOT NULL,
                title TEXT,
                PRIMARY KEY (edition, start_time)
            )
        """)


def write_frames(connection: sqlite3.Connection, edition: str,
                 frames: list[tuple]) -> None:
    """Frames of one edition, each as (frame_index, hash_md5, then the
    picture hashes in the order of PICTURE_COLUMNS, as many as there are)."""
    width = 2 + len(PICTURE_COLUMNS)
    connection.executemany(
        f"INSERT INTO frame_hashes (edition, frame_index, hash_md5, {', '.join(PICTURE_COLUMNS)}) "
        f"VALUES ({', '.join('?' * (width + 1))})",
        [(edition, *frame, *([None] * (width - len(frame)))) for frame in frames])


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


# --- pictures ----------------------------------------------------------------

def create_pictures_table(connection: sqlite3.Connection) -> None:
    """Each frame's picture: where its black bars were cut, and its block averages.

    The bars are kept both as counted and as cut, since a dark picture counts
    as more bar than it has and is cut as its neighbours were. The block
    averages are those of the picture between the bars cut, 16 by 16 blocks
    of it in grey, each kept as the sum of the block's 256 pixels so that no
    rounding is done: divide by 256 for the average.
    """
    connection.execute("""
        CREATE TABLE IF NOT EXISTS frame_pictures (
            edition TEXT NOT NULL,
            frame_index INTEGER NOT NULL,
            top INTEGER NOT NULL,
            bottom INTEGER NOT NULL,
            left INTEGER NOT NULL,
            right INTEGER NOT NULL,
            top_counted INTEGER NOT NULL,
            bottom_counted INTEGER NOT NULL,
            left_counted INTEGER NOT NULL,
            right_counted INTEGER NOT NULL,
            block_averages BLOB NOT NULL,
            PRIMARY KEY (edition, frame_index)
        )
    """)


def write_pictures(connection: sqlite3.Connection, edition: str, pictures: list[tuple]) -> None:
    """Pictures of one edition, each as (frame_index, the bars cut as top,
    bottom, left, right, the bars counted likewise, block averages)."""
    connection.executemany(
        "INSERT OR REPLACE INTO frame_pictures VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [(edition, *picture) for picture in pictures])


def pictures_missing(connection: sqlite3.Connection, edition: str, frame_count: int) -> list[tuple[int, int]]:
    """The stretches of frames, as (start, end), that have no picture yet."""
    have = [row[0] for row in connection.execute(
        "SELECT frame_index FROM frame_pictures WHERE edition = ? ORDER BY frame_index", (edition,))]
    missing, start = [], 0
    for index in have + [frame_count]:
        if index > start:
            missing.append((start, min(index, frame_count)))
        start = max(start, index + 1)
    return [(a, b) for a, b in missing if a < b]


def frame_count_hashed(connection: sqlite3.Connection, edition: str) -> int:
    """How many frames of this edition are hashed."""
    return connection.execute(
        "SELECT COUNT(*) FROM frame_hashes WHERE edition = ?", (edition,)).fetchone()[0]
