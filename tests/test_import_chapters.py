"""Tests for the chapter import module."""

import os
import sys
import sqlite3
from contextlib import closing

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from movie_edition_comparer.db import CHAPTERS_TABLE
from movie_edition_comparer.import_chapters import (
    create_table,
    read_chapters,
    save_chapters_to_table,
)

VALID_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<Chapters>
  <EditionEntry>
    <ChapterAtom>
      <ChapterTimeStart>00:00:00.000</ChapterTimeStart>
      <ChapterDisplay>
        <ChapterString>Prologue</ChapterString>
      </ChapterDisplay>
    </ChapterAtom>
    <ChapterAtom>
      <ChapterTimeStart>00:05:30.000</ChapterTimeStart>
      <ChapterDisplay>
        <ChapterString>The Shire</ChapterString>
      </ChapterDisplay>
    </ChapterAtom>
  </EditionEntry>
</Chapters>
"""


@pytest.fixture
def xml_path(tmp_path):
    """Write valid chapter XML to a temp file."""
    path = tmp_path / "chapters.xml"
    path.write_text(VALID_XML)
    return str(path)


@pytest.fixture
def db_path(tmp_path):
    """Create a temp database with the chapters table."""
    path = str(tmp_path / "test.db")
    create_table(path)
    return path


# ---------------------------------------------------------------------------
# create_table
# ---------------------------------------------------------------------------

class TestCreateTable:
    def test_creates_chapters_table(self, db_path):
        with closing(sqlite3.connect(db_path)) as conn:
            cursor = conn.execute(
                f"SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                (CHAPTERS_TABLE,),
            )
            assert cursor.fetchone() is not None

    def test_table_has_expected_columns(self, db_path):
        with closing(sqlite3.connect(db_path)) as conn:
            cursor = conn.execute(f"PRAGMA table_info({CHAPTERS_TABLE})")
            columns = {row[1] for row in cursor.fetchall()}
        assert columns == {"edition", "start_time", "title"}

    def test_idempotent(self, db_path):
        """Calling create_table twice should not error."""
        create_table(db_path)


# ---------------------------------------------------------------------------
# read_chapters
# ---------------------------------------------------------------------------

class TestReadChapters:
    def test_reads_valid_xml(self, xml_path):
        chapters = list(read_chapters(xml_path))
        assert chapters == [
            ("00:00:00.000", "Prologue"),
            ("00:05:30.000", "The Shire"),
        ]

    def test_wrong_root_element(self, tmp_path):
        path = tmp_path / "bad.xml"
        path.write_text("<NotChapters></NotChapters>")
        with pytest.raises(ValueError, match="root element Chapters"):
            list(read_chapters(str(path)))

    def test_missing_edition_entry(self, tmp_path):
        path = tmp_path / "bad.xml"
        path.write_text("<Chapters></Chapters>")
        with pytest.raises(ValueError, match="EditionEntry"):
            list(read_chapters(str(path)))

    def test_missing_chapter_display(self, tmp_path):
        path = tmp_path / "bad.xml"
        path.write_text(
            "<Chapters><EditionEntry>"
            "<ChapterAtom><ChapterTimeStart>00:00:00</ChapterTimeStart></ChapterAtom>"
            "</EditionEntry></Chapters>"
        )
        with pytest.raises(ValueError, match="ChapterDisplay"):
            list(read_chapters(str(path)))


# ---------------------------------------------------------------------------
# save_chapters_to_table
# ---------------------------------------------------------------------------

class TestSaveChaptersToTable:
    def test_inserts_chapters(self, db_path):
        chapters = [("00:00:00.000", "Prologue"), ("00:05:30.000", "The Shire")]
        save_chapters_to_table(chapters, db_path, "theatrical")

        with closing(sqlite3.connect(db_path)) as conn:
            rows = conn.execute(
                f"SELECT edition, start_time, title FROM {CHAPTERS_TABLE} ORDER BY start_time"
            ).fetchall()
        assert rows == [
            ("theatrical", "00:00:00.000", "Prologue"),
            ("theatrical", "00:05:30.000", "The Shire"),
        ]

    def test_editions_are_isolated(self, db_path):
        save_chapters_to_table([("00:00:00", "Ch1")], db_path, "theatrical")
        save_chapters_to_table([("00:00:00", "Ch1 Extended")], db_path, "extended")

        with closing(sqlite3.connect(db_path)) as conn:
            rows = conn.execute(
                f"SELECT edition, title FROM {CHAPTERS_TABLE} ORDER BY edition"
            ).fetchall()
        assert rows == [
            ("extended", "Ch1 Extended"),
            ("theatrical", "Ch1"),
        ]
