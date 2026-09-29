"""Drives this project's comparer over a scenario's two editions.

The editions are written into a database in the shape compare_hashes expects,
so the scenarios exercise the real query and the real matching rather than a
stand-in for either.
"""

import os
import sqlite3
import tempfile
from contextlib import closing

from movie_edition_comparer import compare_hashes
from movie_edition_comparer.db import create_database, write_frames
from tests.scenarios.editions import Moved

# One frame per second, so a timestamp in seconds is a frame number.
compare_hashes.fps = 1.0

EDITION_A, EDITION_B = "edition_a", "edition_b"


def _write(path: str, a_frames: list[tuple[str, str]], b_frames: list[tuple[str, str]]) -> None:
    """Both hashes go in, as hash_video writes them: what the pixels are, and
    what the frame looks like."""
    create_database(path)
    with closing(sqlite3.connect(path)) as connection:
        for edition, frames in ((EDITION_A, a_frames), (EDITION_B, b_frames)):
            write_frames(connection, edition,
                         [(i, md5, perceptual) for i, (md5, perceptual) in enumerate(frames)])
        connection.commit()


def _reported(item):
    """One thing the comparer reported, as a scenario talks about it."""
    if isinstance(item, compare_hashes.Move):
        return Moved(frames=item.count, at=item.a_start, to=item.b_start)
    return _boundaries(item)


def _boundaries(difference) -> tuple[int, int, int, int]:
    """A difference as the matching frames either side of it.

    compare_hashes reports the differing frames themselves, so the frames
    either side are one before the first and one after the last, which is what
    a scenario talks about.
    """
    return (difference.a.start - 1, difference.a.start + difference.a.count,
            difference.b.start - 1, difference.b.start + difference.b.count)


def compare(a_frames: list[str], b_frames: list[str]) -> list:
    """Every difference the comparer reports between two editions."""
    with tempfile.TemporaryDirectory() as folder:
        path = os.path.join(folder, "frames.db")
        _write(path, a_frames, b_frames)
        return [_reported(item)
                for item in compare_hashes.compare_editions(path, EDITION_A, EDITION_B)]
