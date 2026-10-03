"""The strider command drives the comparer from the command line alone."""

import hashlib
import json
import sqlite3
from contextlib import closing

from movie_edition_comparer import cli
from movie_edition_comparer.db import create_database, write_frames


def _frames(letters: str) -> list[tuple[int, str, str]]:
    """A frame per letter, hashed as hash_video would hash it: 128 bits of
    pixels and 256 bits of picture."""
    return [(index, hashlib.md5(letter.encode()).hexdigest(), hashlib.sha256(letter.encode()).hexdigest())
            for index, letter in enumerate(letters)]


def _film(tmp_path) -> str:
    """Three frames in the theatrical edition; the extended adds one between the last two."""
    path = str(tmp_path / "film.db")
    create_database(path)
    with closing(sqlite3.connect(path)) as connection:
        write_frames(connection, "theatrical", _frames("abc"))
        write_frames(connection, "extended", _frames("abxc"))
        connection.commit()
    return path


def test_compare_reports_from_the_database_named(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr("sys.argv", [
        "strider", "compare", "--db", _film(tmp_path),
        "--edition-a", "theatrical", "--edition-b", "extended", "--json"])
    cli.main()
    out = capsys.readouterr().out
    assert "Count (1): 1 added" in out
    assert json.loads(out.splitlines()[-1]) == [
        {"type": "added",
         "a": {"start": 2, "count": 0, "time": "0:00:00.08"},
         "b": {"start": 2, "count": 1, "time": "0:00:00.08"},
         "bits_apart": None, "bits": []}]


def test_compare_reports_footage_that_moved_as_a_row(tmp_path, monkeypatch, capsys):
    path = str(tmp_path / "film.db")
    create_database(path)
    with closing(sqlite3.connect(path)) as connection:
        write_frames(connection, "theatrical", _frames("abcd"))
        write_frames(connection, "extended", _frames("acdb"))
        connection.commit()
    monkeypatch.setattr("sys.argv", [
        "strider", "compare", "--db", path, "--edition-a", "theatrical", "--edition-b", "extended", "--json"])
    cli.main()
    out = capsys.readouterr().out
    assert "Count (1): 1 moved" in out
    assert "| moved  |" in out
    assert json.loads(out.splitlines()[-1]) == [
        {"type": "moved",
         "a": {"start": 1, "count": 1, "time": "0:00:00.04"},
         "b": {"start": 3, "count": 1, "time": "0:00:00.13"},
         "bits_apart": None, "bits": []}]


def test_compare_needs_both_editions(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr("sys.argv", [
        "strider", "compare", "--db", _film(tmp_path), "--edition-a", "theatrical"])
    try:
        cli.main()
    except SystemExit as left:
        assert left.code == 2
    else:
        raise AssertionError("ran without an edition to compare against")
    assert "--edition-b" in capsys.readouterr().err
