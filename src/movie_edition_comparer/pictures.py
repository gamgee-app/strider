"""A frame's picture: found between its black bars, and kept as block averages.

A film is letterboxed, and some films change their bars as they go: a scene
in 16:9 inside a 2.39:1 film, credits pillarboxed at 4:3. Every frame's bars
are counted afresh. Rows and columns whose brightest pixel is under BLACK
are bar, counted in from each edge. A dark picture counts as more bar than
it has, so a count is cut at the nearest standard bar within SNAP rows, and
a frame with nothing standard near is cut at the film's own letterbox.

Of the picture between the bars cut, the block averages: 16 by 16 blocks,
in grey, of the picture scaled to 256 by 256 as OpenCV's block mean hash
scales it. They are what block mean 0 compares with their median and keeps
a bit of; here every block is kept whole, as the sum of its 256 pixels.
"""

import cv2
import numpy as np
from numpy import ndarray

# Brighter than this, a row or column is picture, not bar.
BLACK = 20

# How far a count may be from a standard bar and still be cut there.
SNAP = 12

# Columns are cut only when both sides agree this closely: a dark picture
# reads as black columns, and the two sides of one seldom agree.
COLUMNS_AGREE = 4

# The flat and 16:9 ratios. The scope ratios, 2.35 to 2.40, lie a few rows
# apart at 2160 rows, so a film's own scope bars are measured instead.
RATIOS = [16 / 9, 1.85, 2.0, 2.2]
PILLARBOX_RATIOS = [4 / 3, 1.66]


def bars_counted(grey: ndarray) -> tuple[int, int, int, int]:
    """Rows of black at the top and bottom, and columns at the left and right."""
    def count(brightest):
        lit = np.flatnonzero(brightest > BLACK)
        return (int(lit[0]), int(len(brightest) - 1 - lit[-1])) if len(lit) else (len(brightest), 0)
    top, bottom = count(grey.max(axis=1))
    left, right = count(grey.max(axis=0))
    return top, bottom, left, right


def _nearest(counted: int, standards: list[int], within: int) -> int | None:
    best = min(standards, key=lambda standard: abs(standard - counted))
    return best if abs(best - counted) <= within else None


class Letterbox:
    """The bars a film of this size can have, and how a frame's count is cut."""

    def __init__(self, width: int, height: int, film_top: int, film_bottom: int):
        self.height = height
        self.default = (film_top, film_bottom, 0, 0)
        def rows(film):
            return sorted({max(0, round((height - width / ratio) / 2)) for ratio in RATIOS} | {film})
        self.top_rows, self.bottom_rows = rows(film_top), rows(film_bottom)
        self.columns = sorted({max(0, round((width - height * ratio) / 2)) for ratio in PILLARBOX_RATIOS}) + [0]

    def cut(self, counted: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
        """Where to cut a frame with these bars counted.

        At the nearest standard bars within SNAP, or where nothing standard
        is near -- a black frame, a dark one -- at the film's own letterbox.
        Never by the frames around it: a frame and its counterpart in another
        edition are then cut alike whatever stands beside each, and frames
        can be measured in any order.
        """
        top_counted, bottom_counted, left_counted, right_counted = counted
        top = _nearest(top_counted, self.top_rows, SNAP)
        bottom = _nearest(bottom_counted, self.bottom_rows, SNAP)
        if top is None or bottom is None or top + bottom >= self.height * 0.6:
            return self.default
        columns = 0
        if abs(left_counted - right_counted) <= COLUMNS_AGREE:
            columns = _nearest(left_counted, self.columns, COLUMNS_AGREE) or 0
        return top, bottom, columns, columns


def film_bars(cap, samples: int = 60) -> tuple[int, int]:
    """The film's own letterbox: the commonest count of black rows at the top
    and at the bottom, over lit frames spread through it. They need not be
    equal, since an odd number of rows of bar cannot be split evenly."""
    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    tops, bottoms = [], []
    for k in range(samples):
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(frame_count * (k + 0.5) / samples))
        ok, frame = cap.read()
        if not ok:
            continue
        grey = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        if grey.mean() < 15:
            continue
        top, bottom, _, _ = bars_counted(grey)
        height = grey.shape[0]
        if 0 < top < height // 4:
            tops.append(top)
        if 0 < bottom < height // 4:
            bottoms.append(bottom)
    mode = lambda counts: max(set(counts), key=counts.count) if counts else 0
    return mode(tops), mode(bottoms)


def block_averages(picture: ndarray) -> bytes:
    """The picture's 16x16 block sums, in grey, as 256 little-endian uint16s."""
    small = cv2.resize(picture, (256, 256), interpolation=cv2.INTER_LINEAR_EXACT)
    grey = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
    sums = grey.reshape(16, 16, 16, 16).sum(axis=(1, 3), dtype=np.uint32)
    return sums.astype("<u2").tobytes()


def averages_of(blob: bytes) -> ndarray:
    """Block averages kept by block_averages, back as 256 grey levels."""
    return np.frombuffer(blob, dtype="<u2").astype(np.float32) / 256


def picture_of(frame: ndarray, cut: tuple[int, int, int, int]) -> ndarray:
    top, bottom, left, right = cut
    return frame[top:frame.shape[0] - bottom, left:frame.shape[1] - right]


def average_frame(frame: ndarray, letterbox: Letterbox) -> tuple[tuple, tuple[int, int, int, int], bytes]:
    """A frame's bars counted, where it is cut, and its block averages."""
    counted = bars_counted(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY))
    cut = letterbox.cut(counted)
    return counted, cut, block_averages(picture_of(frame, cut))


def picture_row(index: int, frame: ndarray, letterbox: Letterbox) -> tuple:
    """A frame's picture as the database keeps it: its index, the bars cut,
    the bars counted, and its block averages."""
    counted, cut, averages = average_frame(frame, letterbox)
    return (index, *cut, *counted, averages)


def letterbox_of(cap) -> "Letterbox | None":
    """The bars a film can have, sampled from the capture; None if it gives no frames.

    The capture is left wherever the sampling took it.
    """
    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
    ok, frame = cap.read()
    if not ok:
        return None
    height, width = frame.shape[:2]
    top, bottom = film_bars(cap)
    return Letterbox(width, height, top, bottom)
