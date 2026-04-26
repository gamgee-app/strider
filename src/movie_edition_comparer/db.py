"""Database access layer for reading frame hashes from SQLite."""

import sqlite3
from contextlib import closing

from movie_edition_comparer.models import FrameHash, FrameMatch, HashFetcher


def read_hashes_from_db(
    db_path: str, edition: str, start: int, end: int,
) -> list[FrameHash]:
    """Read frame hashes from the database for a given index range [start, end)."""
    with closing(sqlite3.connect(db_path)) as connection:
        cursor = connection.cursor()
        cursor.execute(
            "SELECT frame_index, hash_block_mean_0 "
            "FROM frame_hashes "
            "WHERE edition = ? AND frame_index >= ? AND frame_index < ?",
            (edition, start, end),
        )
        return [FrameHash(row[0], row[1]) for row in cursor.fetchall()]


def make_db_fetcher(db_path: str, edition: str) -> HashFetcher:
    """Create a HashFetcher backed by a SQLite database."""
    def fetcher(start: int, end: int) -> list[FrameHash]:
        return read_hashes_from_db(db_path, edition, start, end)
    return fetcher


def fetch_md5_landmarks(
    db_path: str, edition: str, center: int,
    min_distinct: int = 5,
) -> list[tuple[int, str]]:
    """Find frames near center with at least min_distinct different MD5 hashes.

    Returns list of (frame_index, md5_hash) with one representative per
    distinct MD5 value, sorted by frame_index.
    """
    window = 20
    with closing(sqlite3.connect(db_path)) as connection:
        cursor = connection.cursor()
        while window < 100_000:
            start = max(0, center - window // 2)
            end = center + window // 2
            cursor.execute(
                "SELECT frame_index, hash_md5 "
                "FROM frame_hashes "
                "WHERE edition = ? AND frame_index >= ? AND frame_index < ? "
                "ORDER BY ABS(frame_index - ?)",
                (edition, start, end, center),
            )
            seen: set[str] = set()
            landmarks: list[tuple[int, str]] = []
            for idx, md5 in cursor:
                if md5 not in seen:
                    seen.add(md5)
                    landmarks.append((idx, md5))
                    if len(landmarks) >= min_distinct:
                        landmarks.sort()
                        return landmarks
            window *= 2

    raise ValueError(
        f"Could not find {min_distinct} distinct MD5 hashes "
        f"near frame {center} for {edition}"
    )


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
        cursor.execute("""
            WITH a_unique AS (
                    SELECT hash_block_mean_0 AS hash
                    FROM frame_hashes
                    WHERE edition = ?
                    GROUP BY hash
                    HAVING count(1) = 1
                ),
                b_unique AS (
                    SELECT hash_block_mean_0 AS hash
                    FROM frame_hashes
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
                a.frame_index, a.hash_block_mean_0,
                b.frame_index, b.hash_block_mean_0
            FROM frame_hashes a
            JOIN frame_hashes b ON a.hash_block_mean_0 = b.hash_block_mean_0
            WHERE a.edition = ?
              AND b.edition = ?
              AND a.hash_block_mean_0 IN (SELECT hash FROM common)
            ORDER BY a.frame_index
        """, (edition_a, edition_b, edition_a, edition_b))
        return [
            FrameMatch(FrameHash(row[0], row[1]), FrameHash(row[2], row[3]))
            for row in cursor.fetchall()
        ]
