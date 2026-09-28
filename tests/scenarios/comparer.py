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


def _write(path: str, a_frames: list[str], b_frames: list[str]) -> None:
    connection = sqlite3.connect(path)
    for table, frames in ((EDITION_A, a_frames), (EDITION_B, b_frames)):
        connection.execute(
            f"CREATE TABLE {table} (frame_index INTEGER, hash_block_mean_0 TEXT)")
        connection.executemany(
            f"INSERT INTO {table} VALUES (?, ?)", list(enumerate(frames)))
    connection.commit()
    connection.close()


def _frames(difference) -> tuple[int, int, int, int]:
    """Frame numbers for a reported difference.

    compare_hashes reports the last frame before a difference and the last
    frame of it, so the closing boundary is one earlier than the matching frame
    that ends the difference. Adding one back gives both boundaries as the
    matching frames either side, which is what a scenario talks about.
    """
    return (
        round(difference.a_range.start.total_seconds()),
        round(difference.a_range.end.total_seconds()) + 1,
        round(difference.b_range.start.total_seconds()),
        round(difference.b_range.end.total_seconds()) + 1,
    )


def compare(a_frames: list[str], b_frames: list[str]) -> list[tuple[int, int, int, int]]:
    """Every difference the comparer reports between two editions."""
    with tempfile.TemporaryDirectory() as folder:
        path = os.path.join(folder, "frames.db")
        _write(path, a_frames, b_frames)

        matches = compare_hashes.read_unique_valid_matches(path, EDITION_A, EDITION_B)
        found = []
        for index in range(len(matches) - 1):
            difference = compare_hashes.match(
                path, EDITION_A, EDITION_B, matches[index + 1], matches[index])
            if difference:
                found.append(_frames(difference))
        return found
