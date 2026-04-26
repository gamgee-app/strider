"""Tests for the database access layer."""

import os
import sys
import sqlite3
from contextlib import closing

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from movie_edition_comparer.db import (
    make_db_fetcher,
    read_hashes_from_db,
    read_unique_matches,
)
from movie_edition_comparer.models import FrameHash, FrameMatch


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def db_path(tmp_path):
    """Create a temporary database with the frame_hashes table and seed data."""
    path = str(tmp_path / "test.db")
    with closing(sqlite3.connect(path)) as conn:
        conn.execute(f"""
            CREATE TABLE frame_hashes (
                edition TEXT NOT NULL,
                frame_index INTEGER NOT NULL,
                hash_block_mean_0 TEXT NOT NULL,
                PRIMARY KEY (edition, frame_index)
            )
        """)
        conn.executemany(
            f"INSERT INTO frame_hashes (edition, frame_index, hash_block_mean_0) VALUES (?, ?, ?)",
            [
                # Edition A: frames 0–4 with unique hashes
                ("theatrical", 0, "aaaa"),
                ("theatrical", 1, "bbbb"),
                ("theatrical", 2, "cccc"),
                ("theatrical", 3, "dddd"),
                ("theatrical", 4, "eeee"),
                # Edition B: frames 0–4, some hashes shared with A
                ("extended", 0, "aaaa"),  # matches theatrical frame 0
                ("extended", 1, "ffff"),  # unique to extended
                ("extended", 2, "cccc"),  # matches theatrical frame 2
                ("extended", 3, "gggg"),  # unique to extended
                ("extended", 4, "eeee"),  # matches theatrical frame 4
            ],
        )
        conn.commit()
    return path


# ---------------------------------------------------------------------------
# read_hashes_from_db
# ---------------------------------------------------------------------------

class TestReadHashesFromDb:
    def test_returns_matching_range(self, db_path):
        result = read_hashes_from_db(db_path, "theatrical", 1, 4)
        assert result == [
            FrameHash(1, "bbbb"),
            FrameHash(2, "cccc"),
            FrameHash(3, "dddd"),
        ]

    def test_empty_range(self, db_path):
        result = read_hashes_from_db(db_path, "theatrical", 10, 20)
        assert result == []

    def test_filters_by_edition(self, db_path):
        result = read_hashes_from_db(db_path, "extended", 1, 2)
        assert result == [FrameHash(1, "ffff")]

    def test_range_is_exclusive_end(self, db_path):
        """End index is exclusive — frame 4 should not be included."""
        result = read_hashes_from_db(db_path, "theatrical", 3, 4)
        assert len(result) == 1
        assert result[0].index == 3


# ---------------------------------------------------------------------------
# make_db_fetcher
# ---------------------------------------------------------------------------

class TestMakeDbFetcher:
    def test_fetcher_returns_hashes(self, db_path):
        fetcher = make_db_fetcher(db_path, "theatrical")
        result = fetcher(0, 2)
        assert result == [
            FrameHash(0, "aaaa"),
            FrameHash(1, "bbbb"),
        ]

    def test_fetcher_scoped_to_edition(self, db_path):
        fetcher_a = make_db_fetcher(db_path, "theatrical")
        fetcher_b = make_db_fetcher(db_path, "extended")
        assert fetcher_a(1, 2) != fetcher_b(1, 2)


# ---------------------------------------------------------------------------
# read_unique_matches
# ---------------------------------------------------------------------------

class TestReadUniqueMatches:
    def test_finds_common_unique_hashes(self, db_path):
        """Should find frames with hashes that appear exactly once in each edition."""
        matches = read_unique_matches(db_path, "theatrical", "extended")
        # Common unique hashes: aaaa (0↔0), cccc (2↔2), eeee (4↔4)
        assert len(matches) == 3
        assert matches[0] == FrameMatch(FrameHash(0, "aaaa"), FrameHash(0, "aaaa"))
        assert matches[1] == FrameMatch(FrameHash(2, "cccc"), FrameHash(2, "cccc"))
        assert matches[2] == FrameMatch(FrameHash(4, "eeee"), FrameHash(4, "eeee"))

    def test_ordered_by_edition_a_frame_index(self, db_path):
        matches = read_unique_matches(db_path, "theatrical", "extended")
        a_indices = [m.a.index for m in matches]
        assert a_indices == sorted(a_indices)

    def test_excludes_duplicate_hashes(self, db_path):
        """If a hash appears more than once in an edition, it's not a match."""
        # Insert a duplicate hash in theatrical
        with closing(sqlite3.connect(db_path)) as conn:
            conn.execute(
                f"INSERT INTO frame_hashes (edition, frame_index, hash_block_mean_0) VALUES (?, ?, ?)",
                ("theatrical", 5, "aaaa"),  # aaaa now appears twice in theatrical
            )
            conn.commit()
        matches = read_unique_matches(db_path, "theatrical", "extended")
        hashes = [m.a.hash for m in matches]
        assert "aaaa" not in hashes  # no longer unique in theatrical

    def test_no_matches_for_disjoint_editions(self, db_path):
        """Editions with no common hashes return empty list."""
        with closing(sqlite3.connect(db_path)) as conn:
            conn.execute(
                f"INSERT INTO frame_hashes (edition, frame_index, hash_block_mean_0) VALUES (?, ?, ?)",
                ("directors_cut", 0, "zzzz"),
            )
            conn.commit()
        matches = read_unique_matches(db_path, "theatrical", "directors_cut")
        assert matches == []

    def test_empty_database(self, tmp_path):
        """An empty table returns no matches."""
        path = str(tmp_path / "empty.db")
        with closing(sqlite3.connect(path)) as conn:
            conn.execute(f"""
                CREATE TABLE frame_hashes (
                    edition TEXT NOT NULL,
                    frame_index INTEGER NOT NULL,
                    hash_block_mean_0 TEXT NOT NULL,
                    PRIMARY KEY (edition, frame_index)
                )
            """)
        matches = read_unique_matches(path, "a", "b")
        assert matches == []
