"""Database access layer for reading frame hashes from SQLite."""

import sqlite3
from contextlib import closing

from movie_edition_comparer.algorithms import HASH_COLUMN
from movie_edition_comparer.models import FrameHash, FrameMatch, HashFetcher

FRAME_HASHES_TABLE = "frame_hashes"
CHAPTERS_TABLE = "chapters"


def read_hashes_from_db(
    db_path: str, edition: str, start: int, end: int,
) -> list[FrameHash]:
    """Read frame hashes from the database for a given index range [start, end)."""
    with closing(sqlite3.connect(db_path)) as connection:
        cursor = connection.cursor()
        cursor.execute(
            f"SELECT frame_index, {HASH_COLUMN} "
            f"FROM {FRAME_HASHES_TABLE} "
            f"WHERE edition = ? AND frame_index >= ? AND frame_index < ?",
            (edition, start, end),
        )
        return [FrameHash(row[0], row[1]) for row in cursor.fetchall()]


def make_db_fetcher(db_path: str, edition: str) -> HashFetcher:
    """Create a HashFetcher backed by a SQLite database."""
    def fetcher(start: int, end: int) -> list[FrameHash]:
        return read_hashes_from_db(db_path, edition, start, end)
    return fetcher


def read_unique_matches(
    db_path: str, edition_a: str, edition_b: str,
) -> list[FrameMatch]:
    """Query all unique frame hash matches between two editions.

    A match is a hash value that appears exactly once in each edition.
    Ordering is NOT filtered here — that is handled by
    filter_to_monotonic() so we can detect reordered scenes.
    """
    with closing(sqlite3.connect(db_path)) as connection:
        cursor = connection.cursor()
        cursor.execute(f"""
            WITH a_unique AS (
                    SELECT {HASH_COLUMN} AS hash
                    FROM {FRAME_HASHES_TABLE}
                    WHERE edition = ?
                    GROUP BY hash
                    HAVING count(1) = 1
                ),
                b_unique AS (
                    SELECT {HASH_COLUMN} AS hash
                    FROM {FRAME_HASHES_TABLE}
                    WHERE edition = ?
                    GROUP BY hash
                    HAVING count(1) = 1
                ),
                common AS (
                    SELECT hash FROM a_unique
                    INTERSECT
                    SELECT hash FROM b_unique
                )
            SELECT
                a.frame_index, a.{HASH_COLUMN},
                b.frame_index, b.{HASH_COLUMN}
            FROM {FRAME_HASHES_TABLE} a
            JOIN {FRAME_HASHES_TABLE} b ON a.{HASH_COLUMN} = b.{HASH_COLUMN}
            WHERE a.edition = ?
              AND b.edition = ?
              AND a.{HASH_COLUMN} IN (SELECT hash FROM common)
            ORDER BY a.frame_index
        """, (edition_a, edition_b, edition_a, edition_b))
        return [
            FrameMatch(FrameHash(row[0], row[1]), FrameHash(row[2], row[3]))
            for row in cursor.fetchall()
        ]
