"""Compare two editions by their block averages, with no picture hash.

The same steps as compare_hashes, taken on the frames' block averages
instead of a picture hash. Frames identical to the pixel are still found by
their pixel hash, since nothing is surer than that; what two frames look
like is only ever read from their block averages:

  1. Runs of the same frame carried by exactly one run each side are linked,
     and links are carried to their neighbours while they stay the same
     frame -- Heckel's anchoring, by the pixel hash.
  2. A run whose nearest picture on the other side is within SAME_PICTURE,
     clearly nearer than the next nearest, and whose partner's nearest is
     it in turn, is linked -- a picture that is one of a kind on both sides.
     Pictures too flat to tell apart are never linked by looks.
  3. Links are carried to their neighbours while they stay the same picture.
  4. Links that cross the rest only because a still shot's frames all look
     alike are undone; what is left between two links that stay in place is
     paired in order, first with first.
  5. Every link is checked as compare_hashes.check_by_averages checks the
     hash comparer's.

The nearest pictures are found among every run on the other side: first by
the averages' 32 most telling directions, which finds a few candidates for
each, then by the averages in full.
"""

from dataclasses import dataclass

import numpy as np
from numpy import ndarray

from movie_edition_comparer import compare_hashes
from movie_edition_comparer.averages import CLOSER, SAME_PICTURE, apart, flat, read_averages
from movie_edition_comparer.compare_hashes import (
    Difference, Move, _extend_links, _link_unique, _moved_runs, check_by_averages, differences_of, same_frame,
)

# How many candidates the coarse search keeps for each run, to be measured in full.
CANDIDATES = 8

# How many directions the coarse search measures in.
DIRECTIONS = 32

# How many runs each side the coarse search measures against each other at
# once. It holds one block of that many distances, so these bound the memory
# it takes however long the two editions are: a film's runs number hundreds
# of thousands, and measuring every one against every other at once would
# take hundreds of gigabytes.
QUERY_CHUNK = 512
BASE_CHUNK = 16_384


@dataclass
class Run:
    """Frames one after another that are the same frame."""
    start: int
    count: int
    data_hash: str

    @property
    def end(self) -> int:
        return self.start + self.count


def runs_of(md5s: list[str]) -> list[Run]:
    runs: list[Run] = []
    for index, md5 in enumerate(md5s):
        if runs and runs[-1].data_hash == md5:
            runs[-1].count += 1
        else:
            runs.append(Run(index, 1, md5))
    return runs


class Alignment(compare_hashes.Alignment):
    """Which run of edition_a is which run of edition_b, with no hash to index."""

    def __init__(self, a_runs, b_runs):
        self.a_runs, self.b_runs = a_runs, b_runs
        self.a_to_b: dict[int, int] = {}
        self.b_to_a: dict[int, int] = {}


class Pictures:
    """What each run looks like: its first frame's block averages.

    The edition's averages are kept as they were read, one row to a frame,
    and a run's picture is taken from them as it is asked for. A film's runs
    are nearly as many as its frames, so holding a second copy of them, one
    row to a run, would be hundreds of megabytes for nothing.
    """

    def __init__(self, averages: ndarray, runs: list[Run]):
        self.averages = averages
        self.starts = np.fromiter((run.start for run in runs), dtype=np.int64, count=len(runs))
        self.flat = flat(averages)[self.starts]

    def __getitem__(self, runs):
        return self.averages[self.starts[runs]]

    def __len__(self) -> int:
        return len(self.starts)


# --- finding the nearest picture -----------------------------------------------

def _directions(a: ndarray, b: ndarray) -> tuple[ndarray, ndarray]:
    """The mean picture, and the directions pictures differ from it in most."""
    rng = np.random.default_rng(0)
    sample = np.concatenate([a[rng.choice(len(a), min(len(a), 10_000), replace=False)],
                             b[rng.choice(len(b), min(len(b), 10_000), replace=False)]])
    mean = sample.mean(axis=0)
    _, _, vt = np.linalg.svd(sample - mean, full_matrices=False)
    return mean, vt[:DIRECTIONS].T


def nearest_two(queries: ndarray, base: ndarray, mean: ndarray, directions: ndarray) -> tuple[ndarray, ndarray, ndarray]:
    """For each query, its nearest picture in base, how far that is, and how
    far the next nearest is.

    The coarse search works a block of queries against a block of base at a
    time, keeping the best CANDIDATES it has seen for each query so far, and
    those candidates are then measured in full.
    """
    best = np.full(len(queries), -1)
    first = np.full(len(queries), np.inf, dtype=np.float32)
    second = np.full(len(queries), np.inf, dtype=np.float32)
    if not len(queries) or not len(base):
        return best, first, second
    q = ((queries - mean) @ directions).astype(np.float32)
    x = ((base - mean) @ directions).astype(np.float32)
    x_norms = (x * x).sum(axis=1)
    k = min(CANDIDATES, len(base))

    for s in range(0, len(q), QUERY_CHUNK):
        rows, taken = q[s:s + QUERY_CHUNK], slice(s, min(s + QUERY_CHUNK, len(q)))
        held_where = np.zeros((len(rows), 0), dtype=np.int64)
        held_far = np.zeros((len(rows), 0), dtype=np.float32)
        for b in range(0, len(x), BASE_CHUNK):
            block = x[b:b + BASE_CHUNK]
            coarse = x_norms[None, b:b + BASE_CHUNK] - 2 * rows @ block.T
            keep = min(k, len(block))
            where = np.argpartition(coarse, keep - 1, axis=1)[:, :keep]
            held_where = np.concatenate([held_where, where + b], axis=1)
            held_far = np.concatenate([held_far, np.take_along_axis(coarse, where, axis=1)], axis=1)
            if held_where.shape[1] > k:
                keep = np.argpartition(held_far, k - 1, axis=1)[:, :k]
                held_where = np.take_along_axis(held_where, keep, axis=1)
                held_far = np.take_along_axis(held_far, keep, axis=1)

        full = apart(queries[taken][:, None, :], base[held_where])
        order = np.argsort(full, axis=1)
        picked = np.take_along_axis(held_where, order, axis=1)
        full = np.take_along_axis(full, order, axis=1)
        best[taken] = picked[:, 0]
        first[taken] = full[:, 0]
        if full.shape[1] > 1:
            second[taken] = full[:, 1]
    return best, first, second


def _link_alike(alignment: Alignment, a_pictures: Pictures, b_pictures: Pictures) -> None:
    """Link runs whose nearest picture is each other, close and clearly closest."""
    a_free = np.array([i for i in alignment.a_free() if not a_pictures.flat[i]], dtype=int)
    b_free = np.array([j for j in alignment.b_free() if not b_pictures.flat[j]], dtype=int)
    if not len(a_free) or not len(b_free):
        return
    a_looks, b_looks = a_pictures[a_free], b_pictures[b_free]
    mean, directions = _directions(a_looks, b_looks)
    a_best, a_first, a_second = nearest_two(a_looks, b_looks, mean, directions)
    b_best, b_first, b_second = nearest_two(b_looks, a_looks, mean, directions)
    del a_looks, b_looks
    for k, i in enumerate(a_free):
        m = a_best[k]
        if a_first[k] > SAME_PICTURE or a_first[k] >= CLOSER * a_second[k]:
            continue
        if b_best[m] != k or b_first[m] >= CLOSER * b_second[m]:
            continue
        alignment.link(int(i), int(b_free[m]))


# --- placing by order ----------------------------------------------------------

def _crossed_by_noise(alignment: Alignment, moved: set[int], a_pictures: Pictures, b_pictures: Pictures) -> list[int]:
    """Links that cross only because a still shot's frames all look alike: a
    single frame each side, not the same frame, alike to the frame beside its
    partner, landing a few frames from where the links around it point."""
    a_runs, b_runs = alignment.a_runs, alignment.b_runs
    def alike(i, j):
        return 0 <= i < len(a_runs) and 0 <= j < len(b_runs) and apart(a_pictures[i], b_pictures[j]) <= SAME_PICTURE
    noise = []
    for i in moved:
        j = alignment.a_to_b[i]
        if a_runs[i].count != 1 or b_runs[j].count != 1 or same_frame(a_runs[i], b_runs[j]):
            continue
        near = any(abs(alignment.a_to_b[k] - j) <= 8
                   for k in range(max(0, i - 4), min(len(a_runs), i + 5))
                   if k in alignment.a_to_b and k not in moved)
        if near and (alike(i, j - 1) or alike(i, j + 1) or alike(i - 1, j) or alike(i + 1, j)):
            noise.append(i)
    return noise


def _link_between(alignment: Alignment, moved: set[int], a_pictures: Pictures, b_pictures: Pictures) -> None:
    """Pair what is left between one anchor and the next, first with first.

    Of the runs between the same two anchors, a run is paired with the first
    after the last paired that is its picture. Not the nearest: where frames
    look alike their likeness can cross while the footage runs in order, and
    nearest-first would pair them crossed. A frame left one off in a still
    shot is put right by check_by_averages, which moves a link only to a
    frame no other is linked to.
    """
    anchors = [(i, j) for i, j in alignment.pairs() if i not in moved]
    fences = [(-1, -1)] + anchors + [(len(alignment.a_runs), len(alignment.b_runs))]
    for (a_left, b_left), (a_right, b_right) in zip(fences, fences[1:]):
        b_between = np.array([j for j in range(b_left + 1, b_right) if j not in alignment.b_to_a], dtype=int)
        if not len(b_between):
            continue
        after = 0
        for i in range(a_left + 1, a_right):
            if i in alignment.a_to_b or after >= len(b_between):
                continue
            distances = apart(a_pictures[i], b_pictures[b_between[after:]])
            alike = np.flatnonzero(distances <= SAME_PICTURE)
            if not len(alike):
                continue
            k = after + int(alike[0])
            alignment.link(i, int(b_between[k]))
            after = k + 1


def compare_runs(a_runs: list[Run], b_runs: list[Run], a_averages: ndarray, b_averages: ndarray) -> list[Difference | Move]:
    """Everything to report between two editions, by their block averages."""
    a_pictures, b_pictures = Pictures(a_averages, a_runs), Pictures(b_averages, b_runs)
    def same_picture(a, b):
        return apart(a_averages[a.start], b_averages[b.start]) <= SAME_PICTURE

    alignment = Alignment(a_runs, b_runs)
    _link_unique(alignment, lambda run: run.data_hash)
    _extend_links(alignment, same_frame)
    _link_alike(alignment, a_pictures, b_pictures)
    _extend_links(alignment, same_picture)

    moved = _moved_runs(alignment)
    for a_index in _crossed_by_noise(alignment, moved, a_pictures, b_pictures):
        alignment.unlink(a_index)
    moved = _moved_runs(alignment)
    _link_between(alignment, moved, a_pictures, b_pictures)
    _extend_links(alignment, same_picture)

    check_by_averages(alignment, a_averages, b_averages)
    moved = _moved_runs(alignment)
    return differences_of(alignment, moved, apart=lambda a, b: hundredths_apart(a_averages, b_averages, a, b))


def hundredths_apart(a_averages, b_averages, a: Run, b: Run) -> int:
    """How far apart two runs are to look at, in hundredths of a grey level."""
    return int(round(float(apart(a_averages[a.start], b_averages[b.start])) * 100))


def read_md5s(db_path: str, edition: str) -> list[str]:
    import sqlite3
    from contextlib import closing
    with closing(sqlite3.connect(db_path)) as connection:
        return [row[0] for row in connection.execute(
            "SELECT hash_md5 FROM frame_hashes WHERE edition = ? ORDER BY frame_index", (edition,))]


def compare_editions(db_path: str, edition_a: str, edition_b: str) -> list[Difference | Move]:
    """Everything to report between two editions of the one film, by their block averages."""
    a_md5s, b_md5s = read_md5s(db_path, edition_a), read_md5s(db_path, edition_b)
    return compare_runs(runs_of(a_md5s), runs_of(b_md5s),
                        read_averages(db_path, edition_a, len(a_md5s)),
                        read_averages(db_path, edition_b, len(b_md5s)))
