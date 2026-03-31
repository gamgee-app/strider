"""Tests for MD5-anchored frame extraction."""

import hashlib
import os
import sqlite3
import sys
from contextlib import closing

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from movie_edition_comparer.algorithms import hash_frame_md5
from movie_edition_comparer.db import FRAME_HASHES_TABLE, fetch_md5_landmarks
from movie_edition_comparer.video import _anchored_extract


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_frame(value: int) -> np.ndarray:
    """Create a small unique frame (2x2 BGR) from an integer."""
    return np.array([[[value & 0xFF, (value >> 8) & 0xFF, (value >> 16) & 0xFF],
                      [0, 0, 0]],
                     [[0, 0, 0],
                      [0, 0, 0]]], dtype=np.uint8)


def _frame_md5(value: int) -> str:
    return hash_frame_md5(_make_frame(value))


class MockCapture:
    """Simulates cv2.VideoCapture with a controllable seek error.

    frame_values is a list where index = frame number.
    When set(CAP_PROP_POS_FRAMES, n) is called, the internal position
    becomes n + seek_error, simulating HEVC seek drift.
    """

    def __init__(self, frame_values: list[int], seek_error: int = 0):
        self.frame_values = frame_values
        self.seek_error = seek_error
        self.pos = 0

    def set(self, prop, value):
        if prop == 1:  # CAP_PROP_POS_FRAMES
            self.pos = int(value) + self.seek_error

    def read(self):
        if 0 <= self.pos < len(self.frame_values):
            frame = _make_frame(self.frame_values[self.pos])
            self.pos += 1
            return True, frame
        self.pos += 1
        return False, None


# ---------------------------------------------------------------------------
# _anchored_extract
# ---------------------------------------------------------------------------

class TestAnchoredExtract:
    """Test the core anchoring logic with a mock video capture."""

    def _make_landmarks(self, frame_values, indices):
        """Build landmarks from known frame values at given indices."""
        return [(i, _frame_md5(frame_values[i])) for i in indices]

    def test_no_seek_error(self):
        """With no seek error, anchoring finds the frame at the exact position."""
        values = list(range(100, 120))  # 20 unique frames
        cap = MockCapture(values, seek_error=0)
        landmarks = self._make_landmarks(values, [8, 9, 10, 11, 12])
        frame, error = _anchored_extract(cap, 10, landmarks)
        assert error == 0
        assert np.array_equal(frame, _make_frame(values[10]))

    def test_positive_seek_error(self):
        """Seek lands after target (positive error)."""
        values = list(range(100, 120))
        cap = MockCapture(values, seek_error=3)
        landmarks = self._make_landmarks(values, [8, 9, 10, 11, 12])
        frame, error = _anchored_extract(cap, 10, landmarks)
        assert error == 3
        assert np.array_equal(frame, _make_frame(values[10]))

    def test_negative_seek_error(self):
        """Seek lands before target (negative error)."""
        values = list(range(100, 120))
        cap = MockCapture(values, seek_error=-2)
        landmarks = self._make_landmarks(values, [8, 9, 10, 11, 12])
        frame, error = _anchored_extract(cap, 10, landmarks)
        assert error == -2
        assert np.array_equal(frame, _make_frame(values[10]))

    def test_max_seek_error_boundary(self):
        """Seek error at the maximum allowed value."""
        values = list(range(100, 130))
        cap = MockCapture(values, seek_error=5)
        landmarks = self._make_landmarks(values, [10, 11, 12, 13, 14])
        frame, error = _anchored_extract(cap, 12, landmarks, max_seek_error=5)
        assert error == 5
        assert np.array_equal(frame, _make_frame(values[12]))

    def test_negative_max_seek_error_boundary(self):
        """Seek error at the negative maximum."""
        values = list(range(100, 130))
        cap = MockCapture(values, seek_error=-5)
        landmarks = self._make_landmarks(values, [10, 11, 12, 13, 14])
        frame, error = _anchored_extract(cap, 12, landmarks, max_seek_error=5)
        assert error == -5
        assert np.array_equal(frame, _make_frame(values[12]))

    def test_target_outside_landmark_range(self):
        """Target frame is not between the landmarks."""
        values = list(range(100, 130))
        cap = MockCapture(values, seek_error=0)
        landmarks = self._make_landmarks(values, [5, 6, 7, 8, 9])
        frame, error = _anchored_extract(cap, 15, landmarks)
        assert error == 0
        assert np.array_equal(frame, _make_frame(values[15]))

    def test_with_duplicate_adjacent_frames(self):
        """Adjacent frames with identical content don't confuse anchoring."""
        # Frames 10-14 are identical (simulating black frames),
        # but frames 5-9 and 15-19 are unique
        values = (list(range(100, 105))        # 0-4: unique
                  + list(range(200, 205))       # 5-9: unique
                  + [999] * 5                   # 10-14: all identical
                  + list(range(300, 305))       # 15-19: unique
                  + list(range(400, 405)))      # 20-24: unique
        cap = MockCapture(values, seek_error=2)
        # Landmarks in the unique regions around the duplicate block
        landmarks = self._make_landmarks(values, [5, 7, 9, 15, 17])
        frame, error = _anchored_extract(cap, 12, landmarks)
        assert error == 2
        # Frame 12 is in the duplicate block — value 999
        assert np.array_equal(frame, _make_frame(999))

    def test_fallback_when_no_anchor(self):
        """When landmarks don't match any shift, returns unverified frame."""
        values = list(range(100, 120))
        cap = MockCapture(values, seek_error=0)
        # Bogus landmarks that won't match anything
        landmarks = [(8, "bad_md5"), (9, "bad_md5_2"), (10, "bad_md5_3"),
                     (11, "bad_md5_4"), (12, "bad_md5_5")]
        frame, error = _anchored_extract(cap, 10, landmarks)
        assert error == 0
        # Still returns a frame (unverified fallback)
        assert frame is not None

    def test_error_beyond_max_returns_fallback(self):
        """Seek error larger than max_seek_error triggers fallback."""
        values = list(range(100, 140))
        cap = MockCapture(values, seek_error=8)  # beyond max of 5
        landmarks = self._make_landmarks(values, [10, 11, 12, 13, 14])
        frame, error = _anchored_extract(cap, 12, landmarks, max_seek_error=5)
        # Can't anchor — error is 0 (fallback)
        assert error == 0
        # Returns something, but it's the wrong frame
        assert frame is not None


# ---------------------------------------------------------------------------
# fetch_md5_landmarks
# ---------------------------------------------------------------------------

@pytest.fixture
def md5_db(tmp_path):
    """Create a DB with hash_md5 column and known frame data."""
    path = str(tmp_path / "test.db")
    with closing(sqlite3.connect(path)) as conn:
        conn.execute(f"""
            CREATE TABLE {FRAME_HASHES_TABLE} (
                edition TEXT NOT NULL,
                frame_index INTEGER NOT NULL,
                hash TEXT NOT NULL,
                hash_md5 TEXT,
                PRIMARY KEY (edition, frame_index)
            )
        """)
        rows = []
        # Frames 0-9: all black (same MD5)
        for i in range(10):
            rows.append(("test_edition", i, "bmh_black", "md5_black"))
        # Frames 10-19: each unique
        for i in range(10, 20):
            rows.append(("test_edition", i, f"bmh_{i}", f"md5_{i}"))
        # Frames 20-24: all grey (same MD5)
        for i in range(20, 25):
            rows.append(("test_edition", i, "bmh_grey", "md5_grey"))
        # Frames 25-34: each unique
        for i in range(25, 35):
            rows.append(("test_edition", i, f"bmh_{i}", f"md5_{i}"))

        conn.executemany(
            f"INSERT INTO {FRAME_HASHES_TABLE} "
            f"(edition, frame_index, hash, hash_md5) VALUES (?, ?, ?, ?)",
            rows,
        )
        conn.commit()
    return path


class TestFetchMd5Landmarks:

    def test_returns_5_distinct(self, md5_db):
        """Returns 5 landmarks with distinct MD5 hashes."""
        landmarks = fetch_md5_landmarks(md5_db, "test_edition", 15)
        assert len(landmarks) == 5
        md5s = [md5 for _, md5 in landmarks]
        assert len(set(md5s)) == 5

    def test_sorted_by_frame_index(self, md5_db):
        landmarks = fetch_md5_landmarks(md5_db, "test_edition", 15)
        indices = [idx for idx, _ in landmarks]
        assert indices == sorted(indices)

    def test_prefers_frames_near_center(self, md5_db):
        """Landmarks should be close to the requested center."""
        landmarks = fetch_md5_landmarks(md5_db, "test_edition", 15)
        indices = [idx for idx, _ in landmarks]
        # All should be in the unique region near 15
        assert all(10 <= idx < 20 for idx in indices)

    def test_expands_window_for_duplicate_region(self, md5_db):
        """When center is in a duplicate region, window expands to find distinct hashes."""
        # Center at frame 5 — in the all-black region (0-9)
        landmarks = fetch_md5_landmarks(md5_db, "test_edition", 5)
        assert len(landmarks) == 5
        md5s = [md5 for _, md5 in landmarks]
        assert len(set(md5s)) == 5

    def test_expands_across_multiple_duplicate_regions(self, md5_db):
        """Center at frame 22 — in the grey region (20-24), unique regions on both sides."""
        landmarks = fetch_md5_landmarks(md5_db, "test_edition", 22)
        assert len(landmarks) == 5
        md5s = [md5 for _, md5 in landmarks]
        assert len(set(md5s)) == 5

    def test_raises_for_unknown_edition(self, md5_db):
        with pytest.raises(ValueError, match="Could not find"):
            fetch_md5_landmarks(md5_db, "nonexistent", 10)
