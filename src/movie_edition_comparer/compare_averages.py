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

Finding a run's nearest picture never means measuring it against every run
on the other side. A link is only made to a picture within SAME_PICTURE that
is clearly nearer than the next, by CLOSER, so nothing further than
SAME_PICTURE / CLOSER away can change what is linked -- and pictures that
near are near along every direction too. So the pictures are laid on a grid
over the directions they differ in most, with cells as wide as that reach,
and each is measured only against those in its own cell and the cells beside
it: every pair within reach is found, and no other is measured in full.
"""

from dataclasses import dataclass

import numpy as np
from numpy import ndarray

from movie_edition_comparer import compare_hashes
from movie_edition_comparer.averages import CLOSER, SAME_PICTURE, apart, flat, read_averages
from movie_edition_comparer.compare_hashes import (
    Difference, Move, _extend_links, _link_unique, _moved_runs, check_by_averages, differences_of, same_frame,
)

# How many directions pictures are measured along before they are measured in
# full: two pictures are no further apart along these than they are in full,
# so a pair too far apart along them is too far apart.
DIRECTIONS = 32

# How many of those directions the grid is laid over. More cells to look in
# against fewer pictures in each: on The Two Towers, four leaves 200 pictures
# to measure for each, against 260,000 with no grid.
GRID = 4

# Candidate pairs measured at once; bounds the memory the search takes.
CHUNK = 500_000


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


_SPAN = 1 << 12                     # grid cells along one direction, centred on the mean picture


def _cells(projected: ndarray, width: float) -> ndarray:
    """The grid cell each picture falls in, as one number."""
    k = np.floor(projected / width).astype(np.int64) + _SPAN // 2
    if (k < 0).any() or (k >= _SPAN).any():
        raise ValueError("a picture lies further from the rest than the grid reaches")
    return (k * (_SPAN ** np.arange(projected.shape[1]))).sum(axis=1)


def within(a_looks: ndarray, b_looks: ndarray, reach: float) -> tuple[ndarray, ndarray, ndarray]:
    """Every pair of an a picture and a b picture no more than reach apart, as
    (a index, b index, how far apart), and no others.

    reach is in grey levels, root mean square over the blocks, as apart
    measures. Pictures are laid on a grid over their GRID most telling
    directions, in cells as wide as reach is in plain distance, and a picture
    is measured only against those in its cell and the cells beside it; along
    the way a pair is dropped as soon as it is too far apart along the first
    eight directions, or the first DIRECTIONS, since two pictures are never
    further apart along some directions than in full.
    """
    empty = (np.zeros(0, np.int64), np.zeros(0, np.int64), np.zeros(0, np.float32))
    if not len(a_looks) or not len(b_looks):
        return empty
    mean, directions = _directions(a_looks, b_looks)
    pa = ((a_looks - mean) @ directions).astype(np.float32)
    pb = ((b_looks - mean) @ directions).astype(np.float32)
    plain = reach * np.sqrt(a_looks.shape[1])            # root mean square to plain distance
    grid = min(GRID, pa.shape[1])
    ka, kb = _cells(pa[:, :grid], plain), _cells(pb[:, :grid], plain)
    oa, ob = np.argsort(ka, kind="stable"), np.argsort(kb, kind="stable")
    ua, sa, ca = np.unique(ka[oa], return_index=True, return_counts=True)
    ub, sb, cb = np.unique(kb[ob], return_index=True, return_counts=True)

    # the cells beside each a cell that hold b pictures
    steps = np.array(np.meshgrid(*[[-1, 0, 1]] * grid, indexing="ij")).reshape(grid, -1).T
    parts = []
    for step in (steps * (_SPAN ** np.arange(grid))).sum(axis=1):
        at = np.minimum(np.searchsorted(ub, ua + step), len(ub) - 1)
        hit = ub[at] == ua + step
        parts.append((sa[hit], ca[hit], sb[at[hit]], cb[at[hit]]))
    qs, qc, bs, bc = (np.concatenate(x) for x in zip(*parts))
    sizes = qc * bc
    ends = np.cumsum(sizes)

    found, limit8, limit = [], plain * plain, plain * plain
    start = 0
    while start < len(sizes):
        stop = max(start + 1, int(np.searchsorted(ends, ends[start] - sizes[start] + CHUNK, side="right")))
        n = sizes[start:stop]
        cell = np.repeat(np.arange(start, stop), n)
        nth = np.arange(n.sum()) - np.repeat(np.cumsum(n) - n, n)
        i = oa[qs[cell] + nth // bc[cell]]
        j = ob[bs[cell] + nth % bc[cell]]
        keep = ((pa[i, :8] - pb[j, :8]) ** 2).sum(axis=1) <= limit8
        i, j = i[keep], j[keep]
        keep = ((pa[i] - pb[j]) ** 2).sum(axis=1) <= limit
        i, j = i[keep], j[keep]
        d = apart(a_looks[i], b_looks[j])
        keep = d <= reach
        found.append((i[keep], j[keep], d[keep].astype(np.float32)))
        start = stop
    return tuple(np.concatenate(x) for x in zip(*found)) if found else empty


def best_two(owner: ndarray, other: ndarray, far: ndarray, n: int) -> tuple[ndarray, ndarray, ndarray]:
    """For each of n pictures, from pairs it is in: its nearest, how far that
    is, and how far the next nearest is -- infinitely far where there is none."""
    best = np.full(n, -1)
    first = np.full(n, np.inf, dtype=np.float32)
    second = np.full(n, np.inf, dtype=np.float32)
    if len(owner):
        o = np.lexsort((far, owner))
        owner, other, far = owner[o], other[o], far[o]
        head = np.r_[0, np.flatnonzero(np.diff(owner)) + 1]
        best[owner[head]], first[owner[head]] = other[head], far[head]
        nxt = head + 1
        ok = nxt < len(owner)
        ok[ok] = owner[nxt[ok]] == owner[head[ok]]
        second[owner[head[ok]]] = far[nxt[ok]]
    return best, first, second


def _link_alike(alignment: Alignment, a_pictures: Pictures, b_pictures: Pictures) -> None:
    """Link runs whose nearest picture is each other, close and clearly closest."""
    a_free = np.array([i for i in alignment.a_free() if not a_pictures.flat[i]], dtype=int)
    b_free = np.array([j for j in alignment.b_free() if not b_pictures.flat[j]], dtype=int)
    if not len(a_free) or not len(b_free):
        return
    # Nothing further than this can be linked or stop a link being made: a
    # link needs its nearest within SAME_PICTURE and nearer by CLOSER than the next.
    i, j, far = within(a_pictures[a_free], b_pictures[b_free], SAME_PICTURE / CLOSER)
    a_best, a_first, a_second = best_two(i, j, far, len(a_free))
    b_best, b_first, b_second = best_two(j, i, far, len(b_free))
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
