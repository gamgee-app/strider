"""The database holds every edition of a film, and gives each back alone."""

import sqlite3
from contextlib import closing

import pytest

from movie_edition_comparer.compare_hashes import Frame, read_frames
from movie_edition_comparer.db import (
    create_database, landmarks_near, write_chapters, write_frames,
)


def _database(tmp_path) -> str:
    path = str(tmp_path / "film.db")
    create_database(path)
    with closing(sqlite3.connect(path)) as connection:
        write_frames(connection, "theatrical", [(0, "m0", "p0"), (1, "m1", "p1")])
        write_frames(connection, "extended", [(0, "m0", "p0"), (1, "mx", "px"), (2, "m1", "p1")])
        write_chapters(connection, "extended", [("00:00:00.000", "Prologue")])
        connection.commit()
    return path


def test_each_edition_is_read_back_on_its_own(tmp_path):
    path = _database(tmp_path)
    assert read_frames(path, "theatrical") == [Frame(0, "m0", "p0"), Frame(1, "m1", "p1")]
    assert read_frames(path, "extended") == [
        Frame(0, "m0", "p0"), Frame(1, "mx", "px"), Frame(2, "m1", "p1")]


def test_frames_come_back_in_order_however_they_went_in(tmp_path):
    path = str(tmp_path / "film.db")
    create_database(path)
    with closing(sqlite3.connect(path)) as connection:
        write_frames(connection, "theatrical", [(2, "m2", "p2"), (0, "m0", "p0"), (1, "m1", "p1")])
        connection.commit()
    assert [frame.index for frame in read_frames(path, "theatrical")] == [0, 1, 2]


def test_an_edition_not_hashed_has_no_frames(tmp_path):
    assert read_frames(_database(tmp_path), "directors_cut") == []


def test_creating_the_database_again_keeps_what_is_in_it(tmp_path):
    path = _database(tmp_path)
    create_database(path)
    assert len(read_frames(path, "extended")) == 3
    with closing(sqlite3.connect(path)) as connection:
        assert connection.execute(
            "SELECT edition, start_time, title FROM chapters").fetchall() == [
            ("extended", "00:00:00.000", "Prologue")]


class TestLandmarksNear:
    """Frames about a place that can be told apart by their pixels."""

    @pytest.fixture
    def film(self, tmp_path) -> str:
        path = str(tmp_path / "film.db")
        create_database(path)
        with closing(sqlite3.connect(path)) as connection:
            write_frames(connection, "theatrical",
                         [(i, "black", "p") for i in range(10)]
                         + [(i, f"m{i}", "p") for i in range(10, 20)]
                         + [(i, "grey", "p") for i in range(20, 25)]
                         + [(i, f"m{i}", "p") for i in range(25, 35)])
            connection.commit()
        return path

    def test_are_told_apart_by_their_pixels(self, film):
        landmarks = landmarks_near(film, "theatrical", 15)
        assert len(landmarks) == 5
        assert len({md5 for _, md5 in landmarks}) == 5

    def test_are_the_nearest_such_frames_in_frame_order(self, film):
        landmarks = landmarks_near(film, "theatrical", 15)
        assert [index for index, _ in landmarks] == [13, 14, 15, 16, 17]

    def test_look_further_when_the_frames_about_the_place_repeat(self, film):
        assert len({md5 for _, md5 in landmarks_near(film, "theatrical", 5)}) == 5
        assert len({md5 for _, md5 in landmarks_near(film, "theatrical", 22)}) == 5

    def test_are_as_many_as_there_are_when_that_is_fewer(self, film):
        assert len(landmarks_near(film, "theatrical", 10, how_many=50)) == 22
        assert landmarks_near(film, "nowhere", 10) == []
