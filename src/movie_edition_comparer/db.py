"""Database access layer for reading frame hashes from SQLite."""

import sqlite3
from contextlib import closing

from movie_edition_comparer.models import FrameHash, FrameMatch, HashFetcher


def read_hashes_from_db(
    db_path: str, table_name: str, start: int, end: int,
) -> list[FrameHash]:
    """Read frame hashes from the database for a given index range [start, end)."""
    with closing(sqlite3.connect(db_path)) as connection:
        cursor = connection.cursor()
        cursor.execute(
            f"SELECT frame_index, hash_block_mean_0 "
            f"FROM {table_name} "
            f"WHERE frame_index >= ? AND frame_index < ?",
            (start, end),
        )
        return [FrameHash(row[0], row[1]) for row in cursor.fetchall()]


def make_db_fetcher(db_path: str, table_name: str) -> HashFetcher:
    """Create a HashFetcher backed by a SQLite database."""
    def fetcher(start: int, end: int) -> list[FrameHash]:
        return read_hashes_from_db(db_path, table_name, start, end)
    return fetcher


def read_unique_matches(
    db_path: str, table_a: str, table_b: str,
) -> list[FrameMatch]:
    """Query all unique frame hash matches between two edition tables.

    A match is a hash value that appears exactly once in each edition.
    Ordering is NOT filtered here — that is handled by
    filter_to_monotonic() so we can detect reordered scenes.
    """
    with closing(sqlite3.connect(db_path)) as connection:
        cursor = connection.cursor()
        cursor.execute(f"""
            WITH a_unique AS (
                    SELECT hash_block_mean_0 AS hash
                    FROM {table_a}
                    GROUP BY hash
                    HAVING count(1) = 1
                ),
                b_unique AS (
                    SELECT hash_block_mean_0 AS hash
                    FROM {table_b}
                    GROUP BY hash
                    HAVING count(1) = 1
                ),
                common AS (
                    SELECT hash FROM a_unique
                    INTERSECT
                    SELECT hash FROM b_unique
                )
            SELECT
                a.frame_index, a.hash_block_mean_0,
                b.frame_index, b.hash_block_mean_0
            FROM {table_a} a
            JOIN {table_b} b ON a.hash_block_mean_0 = b.hash_block_mean_0
            WHERE a.hash_block_mean_0 IN common
            ORDER BY a.frame_index
        """)
        return [
            FrameMatch(FrameHash(row[0], row[1]), FrameHash(row[2], row[3]))
            for row in cursor.fetchall()
        ]
