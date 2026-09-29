"""The database holds every edition of a film, and gives each back alone."""

import sqlite3
from contextlib import closing

from movie_edition_comparer.compare_hashes import Frame, read_frames
from movie_edition_comparer.db import create_database, write_chapters, write_frames


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
