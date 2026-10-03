"""How alike two frames' pictures are, by their block averages.

Every frame's picture, bars cut away, is kept as 16x16 block averages by
strider average. Two renderings of one picture have block averages a few
hundredths of a grey level apart; two frames a frame apart in a slow shot,
tenths or more; two different pictures, tens. So how far apart two frames
are is the root mean square of the 256 differences, in grey levels, and
frames are the same picture within SAME_PICTURE of each other.
"""

import sqlite3
from contextlib import closing

import numpy as np
from numpy import ndarray

# Two frames this far apart or closer are the same picture. Measured on
# The Two Towers: 169,028 pairs of frames placed by where they sit between
# frames identical to the pixel are all within half a grey level save 55,
# which are over 2 and are not the same picture; frames a frame apart in
# the same shot are mostly over a grey level.
SAME_PICTURE = 1.0

# A link is moved to a frame beside it only if that frame is this much
# closer: a still shot's frames are all near alike, and only a clearly
# closer one is the better partner.
CLOSER = 0.8

# A picture whose blocks vary by less than this, in grey levels, is too
# flat to place by its looks: one black frame is as near another as its own.
FLAT = 2.0


def read_averages(db_path: str, edition: str, frame_count: int) -> ndarray:
    """An edition's block averages, one row of 256 grey levels for each frame."""
    with closing(sqlite3.connect(db_path)) as connection:
        rows = connection.execute(
            "SELECT frame_index, block_averages FROM frame_pictures WHERE edition = ? ORDER BY frame_index",
            (edition,)).fetchall()
    if len(rows) != frame_count or (rows and rows[-1][0] != frame_count - 1):
        raise ValueError(f"{edition} has block averages for {len(rows)} of its {frame_count} frames; "
                         f"run strider average on it first")
    sums = np.frombuffer(b"".join(blob for _, blob in rows), dtype="<u2").reshape(len(rows), 256)
    return sums.astype(np.float32) / 256


def apart(a: ndarray, b: ndarray) -> ndarray:
    """How far apart pictures are: the root mean square of their blocks' differences."""
    return np.sqrt(((a - b) ** 2).mean(axis=-1))


def flat(averages: ndarray) -> ndarray:
    """Which pictures are too flat to place by their looks."""
    return averages.std(axis=-1) < FLAT
