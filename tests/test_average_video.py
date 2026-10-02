"""Every frame's picture is found between its bars, and its block averages kept exactly."""

import sqlite3
from contextlib import closing

import cv2
import numpy as np
import pytest

from movie_edition_comparer.algorithms import hash_md5
from movie_edition_comparer.average_video import average_stretches, share
from movie_edition_comparer.pictures import Letterbox, averages_of, bars_counted, block_averages
from movie_edition_comparer.db import create_database, create_pictures_table, pictures_missing, write_frames

W, H = 384, 216                # a 4K frame at a tenth of the size
FILM = (28, 28)                # 2.39:1 inside 16:9


def letterboxed(value: int, top: int = FILM[0], bottom: int = FILM[1], left: int = 0, right: int = 0) -> np.ndarray:
    """A frame of black bars around a picture that spells out a number."""
    frame = np.zeros((H, W, 3), dtype=np.uint8)
    rng = np.random.default_rng(value)
    frame[top:H - bottom, left:W - right] = rng.integers(40, 250, (H - top - bottom, W - left - right, 3))
    return frame


class TestBars:
    def test_are_counted_in_from_each_edge(self):
        assert bars_counted(cv2.cvtColor(letterboxed(1, 30, 26, 10, 12), cv2.COLOR_BGR2GRAY)) == (30, 26, 10, 12)

    def test_a_black_frame_is_all_bar(self):
        assert bars_counted(np.zeros((H, W), dtype=np.uint8))[0] == H


class TestCut:
    letterbox = Letterbox(W, H, *FILM)

    def test_a_count_near_the_films_bars_is_cut_at_them(self):
        assert self.letterbox.cut((31, 25, 0, 0)) == (28, 28, 0, 0)

    def test_a_frame_in_16_9_is_cut_at_nothing(self):
        assert self.letterbox.cut((0, 0, 0, 0)) == (0, 0, 0, 0)

    def test_a_count_near_nothing_standard_is_cut_at_the_films_letterbox(self):
        assert self.letterbox.cut((60, 60, 0, 0)) == (28, 28, 0, 0)

    def test_a_black_frame_is_cut_at_the_films_letterbox(self):
        assert self.letterbox.cut((H, 0, W, 0)) == (28, 28, 0, 0)

    def test_columns_are_cut_where_both_sides_agree_on_a_pillarbox(self):
        pillar = round((W - H * 4 / 3) / 2)
        assert self.letterbox.cut((0, 0, pillar + 1, pillar - 1)) == (0, 0, pillar, pillar)

    def test_columns_are_not_cut_where_the_sides_disagree(self):
        pillar = round((W - H * 4 / 3) / 2)
        assert self.letterbox.cut((28, 28, pillar, 3)) == (28, 28, 0, 0)


class TestBlockAverages:
    def test_of_a_flat_picture_are_its_grey(self):
        assert np.all(averages_of(block_averages(np.full((100, 300, 3), 77, dtype=np.uint8))) == 77)

    def test_are_the_block_means_of_the_picture_at_256_by_256_without_rounding(self):
        picture = letterboxed(5)[28:H - 28]
        grey = cv2.cvtColor(cv2.resize(picture, (256, 256), interpolation=cv2.INTER_LINEAR_EXACT), cv2.COLOR_BGR2GRAY)
        means = grey.reshape(16, 16, 16, 16).mean(axis=(1, 3)).flatten()
        assert np.array_equal(averages_of(block_averages(picture)), means.astype(np.float32))

    def test_take_256_values_in_512_bytes(self):
        assert len(block_averages(letterboxed(2))) == 512


class TestShare:
    def test_covers_every_missing_frame_once(self):
        missing = [(0, 10), (15, 40), (50, 51)]
        shares = share(missing, 4)
        frames = [i for s in shares for a, b in s for i in range(a, b)]
        assert frames == [i for a, b in missing for i in range(a, b)]

    def test_is_as_even_as_the_frames_allow(self):
        assert [sum(b - a for a, b in s) for s in share([(0, 100)], 3)] == [34, 34, 32]

    def test_of_nothing_is_nothing(self):
        assert share([], 4) == []


class Video:
    """A video of letterboxed frames that seeks exactly, and counts what it reads."""

    def __init__(self, frames):
        self.frames, self.position, self.reads = frames, 0, 0

    def read(self):
        self.reads += 1
        if self.position < len(self.frames):
            self.position += 1
            return True, self.frames[self.position - 1]
        return False, None


def seek(video, target, db_path, edition):
    video.position = target


def hashed(frames, tmp_path) -> str:
    path = str(tmp_path / "film.db")
    create_database(path)
    with closing(sqlite3.connect(path)) as connection:
        write_frames(connection, "theatrical", [(i, hash_md5(f), "00") for i, f in enumerate(frames)])
        create_pictures_table(connection)
        connection.commit()
    return path


FRAMES = [letterboxed(i) for i in range(30)] + [letterboxed(i, 0, 0) for i in range(30, 40)]


class TestAveraging:
    letterbox = Letterbox(W, H, *FILM)

    def stored(self, path):
        with closing(sqlite3.connect(path)) as connection:
            return connection.execute("SELECT frame_index, top, bottom, block_averages FROM frame_pictures "
                                      "WHERE edition = 'theatrical' ORDER BY frame_index").fetchall()

    def test_keeps_every_frames_cut_and_averages(self, tmp_path):
        path = hashed(FRAMES, tmp_path)
        average_stretches(Video(FRAMES), [(0, 40)], path, "theatrical", self.letterbox, seek)
        rows = self.stored(path)
        assert [r[0] for r in rows] == list(range(40))
        assert {(r[1], r[2]) for r in rows[:30]} == {FILM} and {(r[1], r[2]) for r in rows[30:]} == {(0, 0)}
        assert rows[7][3] == block_averages(FRAMES[7][28:H - 28])

    def test_a_second_run_reads_only_what_is_missing(self, tmp_path):
        path = hashed(FRAMES, tmp_path)
        average_stretches(Video(FRAMES), [(0, 12), (20, 40)], path, "theatrical", self.letterbox, seek)
        with closing(sqlite3.connect(path)) as connection:
            missing = pictures_missing(connection, "theatrical", len(FRAMES))
        assert missing == [(12, 20)]
        video = Video(FRAMES)
        average_stretches(video, missing, path, "theatrical", self.letterbox, seek)
        assert video.reads == 8 and len(self.stored(path)) == 40

    def test_a_reader_that_has_lost_its_place_stops(self, tmp_path, monkeypatch):
        monkeypatch.setattr("movie_edition_comparer.average_video.CHECK_EVERY", 10)
        path = hashed(FRAMES, tmp_path)
        def seek_one_off(video, target, db_path, edition):
            video.position = target + 1
        with pytest.raises(RuntimeError, match="lost its place"):
            average_stretches(Video(FRAMES), [(5, 40)], path, "theatrical", self.letterbox, seek_one_off)
