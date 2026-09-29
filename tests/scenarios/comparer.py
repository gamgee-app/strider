"""Drives this project's comparer over a scenario's two editions.

The editions are written into a database in the shape compare_hashes expects,
so the scenarios exercise the real query and the real matching rather than a
stand-in for either.
"""

import os
import sqlite3
import sys
import tempfile

# compare_hashes imports algorithms directly, so its own directory has to be
# importable rather than the package around it.
sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "src", "movie_edition_comparer"))

import compare_hashes  # noqa: E402

# One frame per second, so a timestamp in seconds is a frame number.
compare_hashes.fps = 1.0

EDITION_A, EDITION_B = "edition_a", "edition_b"


def _write(path: str, a_frames: list[tuple[str, str]], b_frames: list[tuple[str, str]]) -> None:
    """Both hashes go in, as hash_video writes them: what the pixels are, and
    what the frame looks like."""
    connection = sqlite3.connect(path)
    for table, frames in ((EDITION_A, a_frames), (EDITION_B, b_frames)):
        connection.execute(
            f"CREATE TABLE {table} "
            f"(frame_index INTEGER, hash_md5 TEXT, hash_block_mean_0 TEXT)")
        connection.executemany(
            f"INSERT INTO {table} VALUES (?, ?, ?)",
            [(i, md5, perceptual) for i, (md5, perceptual) in enumerate(frames)])
    connection.commit()
    connection.close()


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
        return [_boundaries(d)
                for d in compare_hashes.compare_editions(path, EDITION_A, EDITION_B)]
