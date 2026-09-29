"""Hashing picks up where it left off, and lands on the right frame doing so."""

import sqlite3
from contextlib import closing

import numpy as np
import pytest

from movie_edition_comparer import hash_video
from movie_edition_comparer.algorithms import hash_md5
from movie_edition_comparer.compare_hashes import read_frames
from movie_edition_comparer.db import create_database, write_frames
from movie_edition_comparer.hash_video import _seek_to, hash_frame, seek_error

CAP_PROP_POS_FRAMES, CAP_PROP_FRAME_COUNT = 1, 7


def frame(value: int) -> np.ndarray:
    """A 2x2 picture whose pixels spell out a number."""
    picture = np.zeros((2, 2, 3), dtype=np.uint8)
    picture[0, 0] = (value & 0xFF, (value >> 8) & 0xFF, (value >> 16) & 0xFF)
    return picture


class Capture:
    """A video whose frames are numbers, and whose seeking is off by a bit.

    Asked to seek to n, it lands at n + drift, as a real decoder does --
    except at the very start of the video, which is always found exactly.
    """

    def __init__(self, values: list[int], drift: int = 0):
        self.values = values
        self.drift = drift
        self.position = 0
        self.reads = 0

    def get(self, prop):
        assert prop == CAP_PROP_FRAME_COUNT
        return len(self.values)

    def set(self, prop, value):
        assert prop == CAP_PROP_POS_FRAMES
        self.position = int(value) + self.drift if value else 0

    def read(self):
        self.reads += 1
        if 0 <= self.position < len(self.values):
            self.position += 1
            return True, frame(self.values[self.position - 1])
        self.position += 1
        return False, None

    def release(self):
        pass


def hashed(values: list[int], upto: int, tmp_path) -> str:
    """A database holding the first upto frames of a video of these values."""
    path = str(tmp_path / "film.db")
    create_database(path)
    with closing(sqlite3.connect(path)) as connection:
        write_frames(connection, "theatrical", [hash_frame(i, frame(v)) for i, v in enumerate(values[:upto])])
        connection.commit()
    return path


DISTINCT = list(range(100, 160))
BLACK_THEN_DISTINCT = [0] * 30 + list(range(100, 130))


class TestSeekError:
    def landmarks(self, values, indexes):
        return [(i, hash_md5(frame(values[i]))) for i in indexes]

    def test_is_where_the_landmarks_turned_up_relative_to_where_they_belong(self):
        read = [hash_md5(frame(v)) for v in DISTINCT[13:30]]  # asked for 10, landed at 13
        assert seek_error(read, 10, self.landmarks(DISTINCT, [15, 20, 25])) == 3

    def test_is_negative_for_landing_short(self):
        read = [hash_md5(frame(v)) for v in DISTINCT[8:30]]
        assert seek_error(read, 10, self.landmarks(DISTINCT, [15, 20, 25])) == -2

    def test_is_nothing_when_the_landmarks_are_not_there(self):
        read = [hash_md5(frame(v)) for v in DISTINCT[10:30]]
        assert seek_error(read, 10, [(15, "not a hash"), (20, "nor this")]) is None

    def test_is_nothing_when_the_landing_is_further_off_than_allowed(self):
        read = [hash_md5(frame(v)) for v in DISTINCT[18:40]]
        assert seek_error(read, 10, self.landmarks(DISTINCT, [20, 25, 30]), max_error=5) is None


class TestSeekTo:
    @pytest.mark.parametrize("drift", [0, 3, -3, 5, -5, 8])
    def test_the_next_read_is_the_frame_asked_for(self, drift, tmp_path):
        path = hashed(DISTINCT, 40, tmp_path)
        cap = Capture(DISTINCT, drift)
        _seek_to(cap, 40, path, "theatrical")
        assert np.array_equal(cap.read()[1], frame(DISTINCT[40]))

    def test_frames_that_repeat_do_not_place_anything(self, tmp_path):
        path = hashed(BLACK_THEN_DISTINCT, 50, tmp_path)
        cap = Capture(BLACK_THEN_DISTINCT, drift=2)
        _seek_to(cap, 50, path, "theatrical")
        assert np.array_equal(cap.read()[1], frame(BLACK_THEN_DISTINCT[50]))

    def test_reads_from_the_start_when_the_target_is_too_near_it_to_place(self, tmp_path, capsys):
        path = hashed(DISTINCT, 3, tmp_path)
        cap = Capture(DISTINCT, drift=2)
        _seek_to(cap, 3, path, "theatrical")
        assert np.array_equal(cap.read()[1], frame(DISTINCT[3]))
        assert "reading from the start" in capsys.readouterr().out


class TestResuming:
    def hash_video_with(self, cap, path, monkeypatch):
        monkeypatch.setattr(hash_video.cv2, "VideoCapture", lambda _: cap)
        hash_video.hash_video_frames_to_db("film.mkv", path, "theatrical", workers=2)

    def test_hashes_every_frame_of_a_fresh_edition(self, tmp_path, monkeypatch):
        path = hashed(DISTINCT, 0, tmp_path)
        self.hash_video_with(Capture(DISTINCT), path, monkeypatch)
        frames = read_frames(path, "theatrical")
        assert [f.index for f in frames] == list(range(60))
        assert [f.data_hash for f in frames] == [hash_md5(frame(v)) for v in DISTINCT]

    def test_carries_on_from_the_last_frame_hashed(self, tmp_path, monkeypatch):
        path = hashed(DISTINCT, 40, tmp_path)
        cap = Capture(DISTINCT, drift=-2)
        self.hash_video_with(cap, path, monkeypatch)
        frames = read_frames(path, "theatrical")
        assert [f.index for f in frames] == list(range(60))
        assert [f.data_hash for f in frames] == [hash_md5(frame(v)) for v in DISTINCT]
        assert cap.reads < 60, "read the whole video again"

    def test_reads_nothing_when_every_frame_is_hashed(self, tmp_path, monkeypatch, capsys):
        path = hashed(DISTINCT, 60, tmp_path)
        cap = Capture(DISTINCT)
        self.hash_video_with(cap, path, monkeypatch)
        assert cap.reads == 0
        assert "Already hashed" in capsys.readouterr().out


def test_chapter_times_are_written_as_matroska_writes_them():
    assert hash_video._timestamp(0) == "00:00:00.000000000"
    assert hash_video._timestamp(3725.5) == "01:02:05.500000000"
