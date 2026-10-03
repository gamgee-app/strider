"""Drives this project's comparer over a scenario's two editions.

The editions are written into a database in the shape compare_hashes expects,
so the scenarios exercise the real query and the real matching rather than a
stand-in for either.
"""

import os
import sqlite3
import tempfile
from contextlib import closing

from movie_edition_comparer import compare_averages, compare_hashes
from movie_edition_comparer.db import create_database, create_pictures_table, write_frames, write_pictures
from tests.scenarios.editions import Moved, block_averages, tokens

EDITION_A, EDITION_B = "edition_a", "edition_b"


def _write(path: str, a_frames: list[tuple], b_frames: list[tuple]) -> None:
    """Both hashes go in, as hash_video writes them: what the pixels are, and
    what the frame looks like; and the frame's block averages, as strider
    average writes them."""
    create_database(path)
    with closing(sqlite3.connect(path)) as connection:
        create_pictures_table(connection)
        for edition, frames in ((EDITION_A, a_frames), (EDITION_B, b_frames)):
            write_frames(connection, edition,
                         [(i, md5, perceptual) for i, (md5, perceptual, _) in enumerate(frames)])
            write_pictures(connection, edition,
                           [(i, 0, 0, 0, 0, 0, 0, 0, 0, averages) for i, (_, _, averages) in enumerate(frames)])
        connection.commit()


def _reported(item):
    """One thing the comparer reported, as a scenario talks about it."""
    if isinstance(item, compare_hashes.Move):
        return Moved(frames=item.count, at=item.a_start, to=item.b_start)
    return _boundaries(item)


def _boundaries(difference) -> tuple[int, int, int, int, str]:
    """A difference as the matching frames either side of it, and its kind.

    compare_hashes reports the differing frames themselves, so the frames
    either side are one before the first and one after the last, which is what
    a scenario talks about.
    """
    return (difference.a.start - 1, difference.a.start + difference.a.count,
            difference.b.start - 1, difference.b.start + difference.b.count,
            difference.kind)


COMPARERS = {
    "by hash": lambda path: compare_hashes.compare_editions(path, EDITION_A, EDITION_B),
    "by hash, checked by averages": lambda path: compare_hashes.compare_editions(
        path, EDITION_A, EDITION_B, with_averages=True),
    "by averages": lambda path: compare_averages.compare_editions(path, EDITION_A, EDITION_B),
}


def compare(scenario, comparer: str = "by hash") -> list:
    """Every difference a comparer reports between a scenario's two editions."""
    a_frames, b_frames = scenario.frames()
    a_frames = [(*f, block_averages(t)) for f, t in zip(a_frames, tokens(scenario.edition_a))]
    b_frames = [(*f, block_averages(t)) for f, t in zip(b_frames, tokens(scenario.edition_b))]
    with tempfile.TemporaryDirectory() as folder:
        path = os.path.join(folder, "frames.db")
        _write(path, a_frames, b_frames)
        return [_reported(item) for item in COMPARERS[comparer](path)]
