"""How alike two frames' pictures are, by their block averages.

Every frame's picture, bars cut away, is kept as 16x16 block averages by
strider average. Two renderings of one picture have block averages a few
hundredths of a grey level apart; two frames a frame apart in a slow shot,
tenths or more; two different pictures, tens. So how far apart two frames
are is the root mean square of the 256 differences, in grey levels, and
frames are the same picture within SAME_PICTURE of each other.

That holds between files of one master. Two masters grade a film apart --
brightness, contrast, colour, an HDR file against SDR -- and their block
averages are grey levels apart on every frame. So frames can be seen by
their structure instead: each frame's blocks measured against its own mean
and spread, leaving out the outermost ring where masters frame differently,
with how each block steps to the next across and down. A regrade leaves that
largely alone. Frames are then the same picture within SAME_STRUCTURE.
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


# Two frames' structures this far apart or closer are the same picture.
# Measured on The Two Towers, frame for frame between the 2020 remaster and
# the original Blu-rays, 4K tone mapped among them: 99% of frames within 0.32,
# and one unrelated frame in 10,000 nearer than 0.6. Between files of one
# master, 99% are within 0.05.
SAME_STRUCTURE = 0.35


def _z(x: ndarray) -> ndarray:
    return (x - x.mean(axis=-1, keepdims=True)) / (x.std(axis=-1, keepdims=True) + 1e-3)


def structure(averages: ndarray) -> ndarray:
    """Each frame's structure: its inner 14x14 blocks against their own mean
    and spread, and the steps between neighbouring blocks across and down,
    weighed alike."""
    n = len(averages)
    blocks = averages.reshape(n, 16, 16)[:, 1:15, 1:15]
    inner = _z(blocks.reshape(n, 14 * 14))
    shape = inner.reshape(n, 14, 14)
    steps = _z(np.concatenate([np.diff(shape, axis=2).reshape(n, 14 * 13),
                               np.diff(shape, axis=1).reshape(n, 13 * 14)], axis=1))
    return (np.concatenate([inner, steps], axis=1) / np.sqrt(2)).astype(np.float32)


class Looks:
    """How a comparison sees an edition's frames: what it measures, how near
    is the same picture, and which frames are too flat to tell apart."""

    def __init__(self, averages: ndarray, kind: str = "grey"):
        self.kind = kind
        self.flat = flat(averages)
        if kind == "grey":
            self.features, self.same = averages, SAME_PICTURE
        elif kind == "structure":
            self.features, self.same = structure(averages), SAME_STRUCTURE
        else:
            raise ValueError(f"no such way to see frames: {kind}")

    def __getitem__(self, index):
        return self.features[index]

    def __len__(self) -> int:
        return len(self.features)


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
