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
from movie_edition_comparer.algorithms import PICTURE_HASHES
from movie_edition_comparer.pictures import block_averages

# The one hash the comparison goes by; the others take a while on thousands of frames.
ONE = {"block_mean_0": PICTURE_HASHES["block_mean_0"]}
from tests.capture import Capture, frame

def hashed(values: list[int], upto: int, tmp_path) -> str:
    """A database holding the first upto frames of a video of these values."""
    path = str(tmp_path / "film.db")
    create_database(path)
    with closing(sqlite3.connect(path)) as connection:
        write_frames(connection, "theatrical", [hash_frame(i, frame(v), ONE) for i, v in enumerate(values[:upto])])
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
        hash_video.hash_video_frames_to_db("film.mkv", path, "theatrical", workers=2, hashes=ONE, averages=False)

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


class PowerCut(Exception):
    """The machine went away in the middle of a read."""


class CutsOut(Capture):
    """A video whose decoding stops at a frame: with a crash, or with the
    file simply ending there while claiming to be longer."""

    def __init__(self, values: list[int], at: int, crash: bool, drift: int = 0):
        super().__init__(values, drift)
        self.at, self.crash = at, crash

    def read(self):
        if self.position >= self.at:
            if self.crash:
                raise PowerCut()
            self.position += 1
            return False, None
        return super().read()


FILM = list(range(1000, 13000))  # twelve thousand frames, more than one batch


class TestBatches:
    """Frames are written every ten thousand, so that an interrupted run
    keeps what it had, and the next picks up at a real resume point: past
    the first margin, with the seek to place."""

    def hash_video_with(self, cap, path, monkeypatch):
        monkeypatch.setattr(hash_video.cv2, "VideoCapture", lambda _: cap)
        hash_video.hash_video_frames_to_db("film.mkv", path, "theatrical", workers=4, hashes=ONE, averages=False)

    def test_a_crash_keeps_every_batch_committed_before_it(self, tmp_path, monkeypatch):
        path = hashed(FILM, 0, tmp_path)
        with pytest.raises(PowerCut):
            self.hash_video_with(CutsOut(FILM, at=10_500, crash=True), path, monkeypatch)
        assert [f.index for f in read_frames(path, "theatrical")] == list(range(10_000)), \
            "one whole batch committed; the frames of the unfinished one lost"

        cap = Capture(FILM, drift=3)
        self.hash_video_with(cap, path, monkeypatch)
        frames = read_frames(path, "theatrical")
        assert [f.index for f in frames] == list(range(12_000))
        assert [f.data_hash for f in frames] == [hash_md5(frame(v)) for v in FILM]
        assert cap.reads < 2_200, "read the film again rather than picking up at 10,000"

    def test_a_film_that_ends_early_keeps_what_was_read(self, tmp_path, monkeypatch):
        path = hashed(FILM, 0, tmp_path)
        self.hash_video_with(CutsOut(FILM, at=10_500, crash=False), path, monkeypatch)
        assert [f.index for f in read_frames(path, "theatrical")] == list(range(10_500)), \
            "the batch that was under way when the film ended is committed too"

        self.hash_video_with(Capture(FILM, drift=-2), path, monkeypatch)
        frames = read_frames(path, "theatrical")
        assert [f.index for f in frames] == list(range(12_000))
        assert [f.data_hash for f in frames] == [hash_md5(frame(v)) for v in FILM]


class Letterboxed(Capture):
    """A video of letterboxed frames, as a film is: rows of black above and below a picture."""

    def frame_at(self, value):
        picture = np.zeros((24, 40, 3), dtype=np.uint8)
        rng = np.random.default_rng(value)
        picture[3:21] = rng.integers(60, 250, (18, 40, 3))
        return picture

    def read(self):
        ok, _ = super().read()
        return (True, self.frame_at(self.values[self.position - 1])) if ok else (False, None)


class TestPictures:
    """Each frame's picture is measured as it is hashed, so the film is read once."""

    def hash_video_with(self, caps, path, monkeypatch, averages=True):
        made = iter(caps)
        monkeypatch.setattr(hash_video.cv2, "VideoCapture", lambda _: next(made))
        hash_video.hash_video_frames_to_db("film.mkv", path, "theatrical", workers=2, hashes=ONE, averages=averages)

    def stored(self, path):
        with closing(sqlite3.connect(path)) as connection:
            return connection.execute("SELECT frame_index, top, bottom, block_averages FROM frame_pictures "
                                      "WHERE edition = 'theatrical' ORDER BY frame_index").fetchall()

    def test_every_frame_hashed_has_its_picture(self, tmp_path, monkeypatch):
        path = hashed(DISTINCT, 0, tmp_path)
        video = Letterboxed(DISTINCT)
        self.hash_video_with([Letterboxed(DISTINCT), video], path, monkeypatch)
        rows = self.stored(path)
        assert [r[0] for r in rows] == list(range(60))
        assert {(r[1], r[2]) for r in rows} == {(3, 3)}, "cut at the film's own bars"
        assert rows[17][3] == block_averages(video.frame_at(DISTINCT[17])[3:21])
        assert video.reads == 60, "the film read once, for hashes and pictures both"

    def test_a_resumed_run_carries_on_the_pictures_too(self, tmp_path, monkeypatch):
        path = hashed(DISTINCT, 0, tmp_path)
        with closing(sqlite3.connect(path)) as connection:
            write_frames(connection, "theatrical", [hash_frame(i, Letterboxed(DISTINCT).frame_at(v), ONE)
                                                    for i, v in enumerate(DISTINCT[:40])])
            connection.commit()
        self.hash_video_with([Letterboxed(DISTINCT), Letterboxed(DISTINCT, drift=-2)], path, monkeypatch)
        assert [r[0] for r in self.stored(path)] == list(range(40, 60)), \
            "pictures for the frames hashed in this run; the 40 hashed before are left for strider average"

    def test_none_are_kept_when_turned_off(self, tmp_path, monkeypatch):
        path = hashed(DISTINCT, 0, tmp_path)
        self.hash_video_with([Letterboxed(DISTINCT)], path, monkeypatch, averages=False)
        assert self.stored(path) == []
        assert [f.index for f in read_frames(path, "theatrical")] == list(range(60))

