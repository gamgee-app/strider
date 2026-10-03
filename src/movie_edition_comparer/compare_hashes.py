"""Compare two editions of a film, frame by frame.

Each frame was hashed twice. hash_md5 says what its pixels are, and is equal
only between frames that are the same frame. hash_block_mean_0 says what it
looks like, and is equal -- or very nearly -- between two renderings of one
picture. Two editions are separate transfers, so footage they share is
ordinarily the same picture carried by different pixels; both hashes are
needed to tell that apart from footage one edition does not have.

Frames that repeat carry nothing on their own, so the unit that gets matched
is a run of them: black between scenes, a fade, a held frame, a static shot.
"""

import argparse
import bisect
import datetime
import itertools
import json
import sqlite3
from collections import Counter, defaultdict
from contextlib import closing
from dataclasses import dataclass, field
from datetime import timedelta

import numpy as np
from tabulate import tabulate

from movie_edition_comparer.algorithms import PICTURE_HASHES
from movie_edition_comparer.video import Source, cut_differences

# Picture hashes this many bits apart or fewer are the same picture.
perceptual_match_threshold = 5


@dataclass(frozen=True)
class Frame:
    """One frame: what its pixels are, and what it looks like."""
    index: int
    data_hash: str
    picture_hash: str


@dataclass
class Run:
    """Frames one after another that are the same frame."""
    start: int
    count: int
    data_hash: str
    picture_hash: str
    # The picture hash as a number, so that how far two pictures are apart
    # is one exclusive-or and a count of the bits left standing.
    picture_bits: int = field(init=False, repr=False, compare=False)

    def __post_init__(self):
        self.picture_bits = int(self.picture_hash, 16)

    @property
    def end(self) -> int:
        return self.start + self.count


@dataclass(frozen=True)
class Frames:
    """A stretch of frames on one side: how many, and where they start."""
    start: int
    count: int

    @property
    def end(self) -> int:
        return self.start + self.count

    def __str__(self) -> str:
        if self.count == 0:
            return f"nothing at {self.start}"
        return f"{self.count} frame{'s' if self.count != 1 else ''} at {self.start}"


@dataclass(frozen=True)
class Difference:
    """A place where the two editions hold different footage, and how.

    added       edition_b has footage edition_a does not
    removed     edition_a has footage edition_b does not
    replaced    each has footage there, and it is not the same picture
    reencoded   the same picture for the same length, carried by other frames
    retimed     the same picture, held for a different length
    """
    a: Frames
    b: Frames
    kind: str
    # How far apart the two sides are to look at, as stretches of (frames,
    # bits): the picture hashes of a re-encoding or a retiming, and of a
    # replacement whose sides are the same length, frame against frame.
    # Empty where one side has nothing, or the sides cannot be laid side by
    # side. Kept so that a report can draw the line between "the same
    # picture" and "another picture" for itself.
    bits: tuple[tuple[int, int], ...] = ()

    def __str__(self) -> str:
        return f"{self.kind:<10} edition_a: {str(self.a):<22} edition_b: {self.b}"

    @property
    def bits_apart(self) -> int | None:
        """The most any frame is from its counterpart, or None if unknown."""
        return max((apart for _, apart in self.bits), default=None)


@dataclass(frozen=True)
class Move:
    """Footage in both editions, in a different place in each.

    Says more than a difference at each of the two places would: it is the
    same footage relocated, not two unrelated stretches that disagree.
    """
    count: int
    a_start: int
    b_start: int

    def __str__(self) -> str:
        plural = "s" if self.count != 1 else ""
        return (f"{self.count} frame{plural} at {self.a_start} in edition_a "
                f"appear at {self.b_start} in edition_b")


def read_frames(db_path: str, edition: str, picture_hash: str = "block_mean_0") -> list[Frame]:
    """An edition's frames, each with its pixel hash and the picture hash named."""
    if picture_hash not in PICTURE_HASHES:
        raise ValueError(f"{picture_hash!r} is not a picture hash; the hashes are {', '.join(PICTURE_HASHES)}")
    with closing(sqlite3.connect(db_path)) as connection:
        cursor = connection.cursor()
        cursor.execute(f"""
            SELECT
                frame_index,
                hash_md5,
                hash_{picture_hash}
            FROM
                frame_hashes
            WHERE
                edition = ?
            ORDER BY
                frame_index
        """, (edition,))
        frames = [Frame(*row) for row in cursor.fetchall()]
    if any(frame.picture_hash is None for frame in frames):
        raise ValueError(f"{edition} was not hashed with {picture_hash}")
    return frames


def runs_of(frames: list[Frame]) -> list[Run]:
    """Frames gathered into runs of the same frame repeated."""
    runs: list[Run] = []
    for frame in frames:
        if runs and runs[-1].data_hash == frame.data_hash and runs[-1].end == frame.index:
            runs[-1].count += 1
        else:
            runs.append(Run(frame.index, 1, frame.data_hash, frame.picture_hash))
    return runs


def bits_apart(a: Run, b: Run) -> int:
    return (a.picture_bits ^ b.picture_bits).bit_count()


def same_frame(a: Run, b: Run) -> bool:
    """The same frame: the very same pixels."""
    return a.data_hash == b.data_hash


def same_picture(a: Run, b: Run) -> bool:
    """The same picture, however its pixels were arrived at."""
    return bits_apart(a, b) <= perceptual_match_threshold


class Alignment:
    """Which run of edition_a is which run of edition_b."""

    def __init__(self, a_runs: list[Run], b_runs: list[Run]):
        self.a_runs = a_runs
        self.b_runs = b_runs
        self.a_to_b: dict[int, int] = {}
        self.b_to_a: dict[int, int] = {}
        self.masks = _piece_masks(a_runs + b_runs)

    def link(self, a_index: int, b_index: int) -> None:
        self.a_to_b[a_index] = b_index
        self.b_to_a[b_index] = a_index

    def unlink(self, a_index: int) -> None:
        del self.b_to_a[self.a_to_b.pop(a_index)]

    def a_free(self) -> list[int]:
        return [i for i in range(len(self.a_runs)) if i not in self.a_to_b]

    def b_free(self) -> list[int]:
        return [j for j in range(len(self.b_runs)) if j not in self.b_to_a]

    def pairs(self) -> list[tuple[int, int]]:
        return sorted(self.a_to_b.items())


def _only_once(indexes: list[int], key_of) -> dict[str, int]:
    """The keys carried by exactly one of these runs, and which run that is."""
    seen: dict[str, int | None] = {}
    for index in indexes:
        key = key_of(index)
        seen[key] = index if key not in seen else None
    return {key: index for key, index in seen.items() if index is not None}


def _link_unique(alignment: Alignment, key_of) -> None:
    """Link runs that carry a key no other unlinked run on either side carries.

    Heckel's anchoring step: a run that is one of a kind in both editions can
    only be itself, so it can be linked without looking at anything around it.
    """
    a_once = _only_once(alignment.a_free(), lambda i: key_of(alignment.a_runs[i]))
    b_once = _only_once(alignment.b_free(), lambda j: key_of(alignment.b_runs[j]))
    for key, a_index in a_once.items():
        if key in b_once:
            alignment.link(a_index, b_index=b_once[key])


def _piece_masks(runs: list[Run]) -> list[int]:
    """The bits of the picture hash that vary across the film, cut into more
    pieces than a match is allowed to differ by bits.

    Two hashes close enough to be one picture have a piece in common, since
    there are more pieces than bits they may differ by. Looking only at runs
    sharing a piece finds every match without reading every pair.

    Only the bits that vary are cut up. The rows above and below a
    letterboxed picture hash the same on every frame, so a piece holding
    them is shared by every frame and finds nothing; and two hashes a few
    bits apart are as few apart on the bits that vary, so leaving the rest
    out loses no match.
    """
    if not runs:
        return [0] * (perceptual_match_threshold + 1)
    hash_bits = len(runs[0].picture_hash) * 4
    hashes = np.frombuffer(b"".join(bytes.fromhex(run.picture_hash) for run in runs),
                           dtype=np.uint8).reshape(len(runs), hash_bits // 8)
    set_in = np.unpackbits(hashes, axis=1).sum(axis=0)
    # unpackbits gives the first byte's high bit first; as a number, that is the top bit.
    varying = sorted(hash_bits - 1 - place for place, count in enumerate(set_in)
               if 0.02 * len(runs) < count < 0.98 * len(runs))
    count = perceptual_match_threshold + 1
    size = -(-len(varying) // count)
    return [sum(1 << bit for bit in varying[piece * size:(piece + 1) * size])
            for piece in range(count)]


def _pieces(run: Run, masks: list[int]) -> list[str]:
    return [f"{piece}:{run.picture_bits & mask:x}" for piece, mask in enumerate(masks)]


def _lookalikes(run: Run, others: list[Run], sharing: dict[str, list[int]],
                masks: list[int], at_most: int) -> list[int]:
    """Which of the others look like this run, up to as many as matter.

    Only runs sharing a piece of the hash are looked at, and looking stops
    once at_most have been found, since past that the answer is the same:
    too many.
    """
    found: list[int] = []
    for piece in _pieces(run, masks):
        for index in sharing.get(piece, ()):
            if index not in found and same_picture(run, others[index]):
                found.append(index)
                if len(found) == at_most:
                    return found
    return found


def _sharing(indexes: list[int], runs: list[Run], masks: list[int]) -> dict[str, list[int]]:
    """Which of these runs carry each piece of hash."""
    sharing = defaultdict(list)
    for index in indexes:
        for piece in _pieces(runs[index], masks):
            sharing[piece].append(index)
    return sharing


def _link_alike(alignment: Alignment) -> None:
    """Link runs that look like one run on the other side and no other.

    What is left once equal hashes have been used up: two renderings of one
    picture that are a bit apart to look at as well. A run that looks like
    two is not placed by looks, so once two are found there is no need to
    go on finding them -- which matters, since a dark frame looks like
    every other dark frame.
    """
    a_free, b_free = alignment.a_free(), alignment.b_free()
    b_sharing = _sharing(b_free, alignment.b_runs, alignment.masks)

    only = {}
    for a_index in a_free:
        alike = _lookalikes(alignment.a_runs[a_index], alignment.b_runs, b_sharing,
                            alignment.masks, at_most=2)
        if len(alike) == 1:
            only[a_index] = alike[0]

    a_sharing = _sharing(a_free, alignment.a_runs, alignment.masks)
    for a_index, b_index in only.items():
        if _lookalikes(alignment.b_runs[b_index], alignment.a_runs, a_sharing,
                       alignment.masks, at_most=2) == [a_index]:
            alignment.link(a_index, b_index)


def _extend_links(alignment: Alignment, matches) -> None:
    """Carry each link out to its neighbours while they still agree.

    Heckel's second step. A run that repeats is one of a kind nowhere, so it
    can only be placed by what it sits between.
    """
    for a_index, b_index in alignment.pairs():
        for step in (1, -1):
            i, j = a_index + step, b_index + step
            while (0 <= i < len(alignment.a_runs) and 0 <= j < len(alignment.b_runs)
                   and i not in alignment.a_to_b and j not in alignment.b_to_a
                   and matches(alignment.a_runs[i], alignment.b_runs[j])):
                alignment.link(i, j)
                i, j = i + step, j + step


def _link_between(alignment: Alignment, moved: set[int]) -> None:
    """Pair what is left between one anchor and the next, first with first.

    A frame that looks like more than one run on the other side is not
    placed by looks. It is placed by where it sits: among the runs standing
    between the same two frames that stayed put, taken in order, it is the
    first that looks like it and stands after whatever was paired last --
    since nothing else can tell two black frames apart. What is placed by
    where it sits cannot then be said to have moved, so this comes after
    the moves are known and cannot make any.
    """
    anchors = [(i, j) for i, j in alignment.pairs() if i not in moved]
    fences = [(-1, -1)] + anchors + [(len(alignment.a_runs), len(alignment.b_runs))]
    for (a_left, b_left), (a_right, b_right) in zip(fences, fences[1:]):
        b_between = [j for j in range(b_left + 1, b_right) if j not in alignment.b_to_a]
        if not b_between:
            continue
        b_sharing = _sharing(b_between, alignment.b_runs, alignment.masks)
        after = b_left
        for i in range(a_left + 1, a_right):
            if i in alignment.a_to_b:
                continue
            j = _first_lookalike_after(alignment.a_runs[i], alignment.b_runs, b_sharing,
                                       alignment.masks, after)
            if j is not None:
                alignment.link(i, j)
                after = j


def _first_lookalike_after(run: Run, others: list[Run], sharing: dict[str, list[int]],
                           masks: list[int], after: int) -> int | None:
    """The first of the others past a place that looks like this run."""
    first = None
    for piece in _pieces(run, masks):
        indexes = sharing.get(piece, ())
        for index in indexes[bisect.bisect_right(indexes, after):]:
            if first is not None and index >= first:
                break
            if same_picture(run, others[index]):
                first = index
                break
    return first


def align(a_runs: list[Run], b_runs: list[Run]) -> Alignment:
    """Pair up the runs the two editions share.

    The same frame is the strongest thing a run can be, so those are matched
    first and a run of them is never given away to a mere rendering of the
    same picture.
    """
    alignment = Alignment(a_runs, b_runs)

    _link_unique(alignment, lambda run: run.data_hash)
    _extend_links(alignment, same_frame)

    _link_unique(alignment, lambda run: run.picture_hash)
    _extend_links(alignment, same_picture)

    _link_alike(alignment)
    _extend_links(alignment, same_picture)

    return alignment


def _rising_lengths(values: list[int]) -> list[int]:
    """For each place, the longest rising run of values ending there."""
    lengths: list[int] = []
    tails: list[int] = []
    for value in values:
        place = bisect.bisect_left(tails, value)
        if place == len(tails):
            tails.append(value)
        else:
            tails[place] = value
        lengths.append(place + 1)
    return lengths


def _moved_runs(alignment: Alignment) -> set[int]:
    """Which runs of edition_a turn up somewhere else in edition_b.

    The footage that stays put is the links that rise together, and a link
    only counts as staying if every longest rising run of links holds it.
    Where two pieces of footage have swapped there is no saying which of them
    is the one that stayed, so both have moved.
    """
    pairs = alignment.pairs()
    if not pairs:
        return set()

    b_indexes = [j for _, j in pairs]
    rising = _rising_lengths(b_indexes)
    falling = list(reversed(_rising_lengths([-j for j in reversed(b_indexes)])))
    longest = max(up + down - 1 for up, down in zip(rising, falling))

    could_stay = [up + down - 1 == longest for up, down in zip(rising, falling)]
    contested = Counter(rising[k] for k in range(len(pairs)) if could_stay[k])
    staying = [k for k in range(len(pairs)) if could_stay[k] and contested[rising[k]] == 1]

    # Footage sitting at the same frame in both editions has not gone anywhere.
    # The links that stay rise together, so each of these joins them wherever
    # it does not cross the ones either side of it.
    for which, (a_index, b_index) in enumerate(pairs):
        if alignment.a_runs[a_index].start != alignment.b_runs[b_index].start:
            continue
        place = bisect.bisect_left(staying, which)
        if place < len(staying) and staying[place] == which:
            continue
        before = pairs[staying[place - 1]][1] if place else -1
        after = pairs[staying[place]][1] if place < len(staying) else float("inf")
        if before < b_index < after:
            staying.insert(place, which)

    return {pairs[k][0] for k in set(range(len(pairs))) - set(staying)}


def _crossed_by_noise(alignment: Alignment, moved: set[int]) -> list[int]:
    """Links that cross only because frames that all look alike were paired
    by which looked most alike.

    Two transfers of a static shot give frames that differ by a bit or two
    from each other in every direction, so the closest match to a frame is
    as likely to be its neighbour's counterpart as its own, and the links
    cross. Nothing moved: the footage is there in order on both sides. Such
    a link -- a single frame each side, alike but not the same frame,
    looking like the frame beside its partner, and landing a few frames from
    where the links around it say it belongs -- is undone, so that the pass
    that pairs what is left in order can put it where it belongs. Footage
    that really moved lands far from where its neighbours' links point, and
    is left alone.
    """
    a_runs, b_runs = alignment.a_runs, alignment.b_runs
    noise = []
    for i in moved:
        j = alignment.a_to_b[i]
        a, b = a_runs[i], b_runs[j]
        if a.count != 1 or b.count != 1 or same_frame(a, b):
            continue
        near = any(abs(alignment.a_to_b[k] - j) <= 8
                   for k in range(max(0, i - 4), min(len(a_runs), i + 5))
                   if k in alignment.a_to_b and k not in moved)
        alike_beside = (any(same_picture(a, b_runs[k]) for k in (j - 1, j + 1) if 0 <= k < len(b_runs))
                        or any(same_picture(a_runs[k], b) for k in (i - 1, i + 1) if 0 <= k < len(a_runs)))
        if near and alike_beside:
            noise.append(i)
    return noise


def _moves(alignment: Alignment, moved: set[int]) -> list[Difference | Move]:
    """Footage that moved, with runs that travelled together reported as one.

    Footage that does not last as long once it gets there has moved only as
    far as both editions hold it. The frames one edition has over and above
    that are a difference standing beside the move, since a move says one
    length and there are two.
    """
    moves: list[Move] = []
    retimed: list[Difference] = []
    previous = None
    for a_index in sorted(moved):
        b_index = alignment.a_to_b[a_index]
        a_run, b_run = alignment.a_runs[a_index], alignment.b_runs[b_index]
        travelled = min(a_run.count, b_run.count)
        alike = a_run.count == b_run.count

        if alike and previous == (a_index - 1, b_index - 1):
            moves[-1] = Move(moves[-1].count + travelled,
                             moves[-1].a_start, moves[-1].b_start)
        else:
            moves.append(Move(travelled, a_run.start, b_run.start))

        if a_run.count > travelled:
            retimed.append(Difference(
                Frames(a_run.start + travelled, a_run.count - travelled),
                Frames(b_run.end, 0), "removed"))
        elif b_run.count > travelled:
            retimed.append(Difference(
                Frames(a_run.end, 0),
                Frames(b_run.start + travelled, b_run.count - travelled), "added"))

        previous = (a_index, b_index) if alike else None
    return moves + retimed


@dataclass(frozen=True)
class _Block:
    """Runs with nothing on the other side to answer for them."""
    run: int
    frames: Frames


def _unmatched_blocks(runs: list[Run], linked: dict[int, int],
                      lower: int, upper: int) -> list[_Block]:
    """Footage between two anchors that the other edition does not have.

    Runs that touch are one piece of footage, so they are reported together
    rather than one difference each.
    """
    blocks: list[_Block] = []
    previous = None
    for index in range(lower, upper):
        if index in linked:
            continue
        if previous == index - 1:
            blocks[-1] = _Block(blocks[-1].run,
                                Frames(blocks[-1].frames.start,
                                       blocks[-1].frames.count + runs[index].count))
        else:
            blocks.append(_Block(index, Frames(runs[index].start, runs[index].count)))
        previous = index
    return blocks


def _would_sit_at(runs: list[Run], linked: dict[int, int],
                  other: list[Run], before: int) -> int:
    """Where footage the other edition does not have would have sat.

    Just after whatever the nearest footage before it turned into, or at the
    very start if there is nothing before it that both editions hold.
    """
    for index in range(before - 1, -1, -1):
        if index in linked:
            return other[linked[index]].end
    return 0


def _difference_of(a: Run, b: Run, apart=None) -> Difference | None:
    """What to report of two runs that hold the same picture.

    Nothing, if they are the same frame for the same length of time. The
    picture being the same is not enough: a re-encoding is footage the two
    editions do not hold identically, and so is footage held longer.
    """
    if same_frame(a, b) and a.count == b.count:
        return None
    return Difference(Frames(a.start, a.count), Frames(b.start, b.count),
                      "reencoded" if a.count == b.count else "retimed",
                      ((a.count, (apart or bits_apart)(a, b)),))


def _at(item: Difference | Move) -> int:
    return item.a_start if isinstance(item, Move) else item.a.start


def compare_runs(a_runs: list[Run], b_runs: list[Run],
                 averages: tuple | None = None) -> list[Difference | Move]:
    """Everything to report between two editions, in the order it comes.

    Given the two editions' block averages, every link the hashes made is
    checked by them before anything is reported.
    """
    alignment = align(a_runs, b_runs)
    moved = _moved_runs(alignment)
    for a_index in _crossed_by_noise(alignment, moved):
        alignment.unlink(a_index)
    moved = _moved_runs(alignment)
    _link_between(alignment, moved)
    _extend_links(alignment, same_picture)
    if averages is not None:
        check_by_averages(alignment, *averages)
        moved = _moved_runs(alignment)
    return differences_of(alignment, moved)


def differences_of(alignment: Alignment, moved: set[int], apart=None) -> list[Difference | Move]:
    """The differences and moves an alignment of the two editions makes.

    apart says how far apart two runs are to look at, for the report; by
    default, the bits their picture hashes are apart.
    """
    apart = apart or bits_apart
    a_runs, b_runs = alignment.a_runs, alignment.b_runs
    anchors = [(i, j) for i, j in alignment.pairs() if i not in moved]
    fences = [(-1, -1)] + anchors + [(len(a_runs), len(b_runs))]

    found: list[Difference | Move] = []
    re_encoding = None  # the last thing found, if it is one and nothing has come since
    for left, right in zip(fences, fences[1:]):
        between = _between(alignment, left, right, apart)
        found += between
        if right[0] < len(a_runs):
            difference = _difference_of(a_runs[right[0]], b_runs[right[1]], apart)
            if difference and re_encoding and not between and _touching(re_encoding, difference):
                found[-1] = re_encoding = _joined(re_encoding, difference)
                continue
            if difference:
                found.append(difference)
            re_encoding = difference if difference and difference.kind == "reencoded" else None
    found += _moves(alignment, moved)
    return sorted(found, key=_at)


def check_by_averages(alignment, a_averages, b_averages) -> None:
    """Check every link by the two editions' block averages, which tell a
    frame from its neighbour where a picture hash cannot.

    A link to a frame that is not its partner's picture is undone; a link
    one or two frames off is moved to the frame that is; and a run left
    unlinked beside a link is tried against the frame its neighbour's link
    says it would have, and linked if that is its picture. The block
    averages of a run are those of its first frame, since its frames are the
    same frame.
    """
    from movie_edition_comparer.averages import CLOSER, SAME_PICTURE, apart

    a_runs, b_runs = alignment.a_runs, alignment.b_runs
    def far(i, j):
        return float(apart(a_averages[a_runs[i].start], b_averages[b_runs[j].start]))

    # Moved first, so that a link put right is the one that is then judged.
    for i, j in alignment.pairs():
        if same_frame(a_runs[i], b_runs[j]):
            continue
        now = far(i, j)
        best, nearest = j, now
        for k in range(max(0, j - 2), min(len(b_runs), j + 3)):
            if k != j and k not in alignment.b_to_a and (d := far(i, k)) < nearest:
                best, nearest = k, d
        if best != j and nearest < CLOSER * now:
            alignment.unlink(i)
            alignment.link(i, best)

    for i, j in alignment.pairs():
        if not same_frame(a_runs[i], b_runs[j]) and far(i, j) > SAME_PICTURE:
            alignment.unlink(i)

    grown = True
    while grown:
        grown = False
        for i, j in alignment.pairs():
            for step in (1, -1):
                k, m = i + step, j + step
                while (0 <= k < len(a_runs) and 0 <= m < len(b_runs)
                       and k not in alignment.a_to_b and m not in alignment.b_to_a
                       and far(k, m) <= SAME_PICTURE):
                    alignment.link(k, m)
                    grown = True
                    k, m = k + step, m + step


def _touching(before: Difference, after: Difference) -> bool:
    """Two re-encodings with nothing between them on either side.

    A transfer re-encodes every frame, so re-encoded frames come in
    stretches, and a stretch is one difference rather than one for each
    frame of it. Only re-encodings join: a frame held for longer is its own
    difference, since a stretch has one length and that has two.
    """
    return (after.kind == "reencoded"
            and before.a.end == after.a.start and before.b.end == after.b.start)


def _joined(before: Difference, after: Difference) -> Difference:
    return Difference(Frames(before.a.start, before.a.count + after.a.count),
                      Frames(before.b.start, before.b.count + after.b.count), "reencoded",
                      _stretches(before.bits + after.bits))


def _stretches(bits: tuple[tuple[int, int], ...]) -> tuple[tuple[int, int], ...]:
    """Stretches of frames the same number of bits apart, run together."""
    out: list[tuple[int, int]] = []
    for frames, apart in bits:
        if out and out[-1][1] == apart:
            out[-1] = (out[-1][0] + frames, apart)
        else:
            out.append((frames, apart))
    return tuple(out)


def _side_by_side(a_runs: list[Run], b_runs: list[Run], apart=None) -> tuple[tuple[int, int], ...]:
    """How far apart two stretches of the same length are, frame against frame."""
    def frames(runs):
        for run in runs:
            for _ in range(run.count):
                yield run
    apart = apart or bits_apart
    return _stretches(tuple((1, apart(a, b)) for a, b in zip(frames(a_runs), frames(b_runs))))


def _between(alignment: Alignment,
             left: tuple[int, int], right: tuple[int, int], apart=None) -> list[Difference]:
    """The differences lying between two anchors."""
    a_blocks = _unmatched_blocks(alignment.a_runs, alignment.a_to_b, left[0] + 1, right[0])
    b_blocks = _unmatched_blocks(alignment.b_runs, alignment.b_to_a, left[1] + 1, right[1])

    found = []
    for a_block, b_block in itertools.zip_longest(a_blocks, b_blocks):
        a_frames = a_block.frames if a_block else Frames(
            _would_sit_at(alignment.b_runs, alignment.b_to_a,
                          alignment.a_runs, b_block.run), 0)
        b_frames = b_block.frames if b_block else Frames(
            _would_sit_at(alignment.a_runs, alignment.a_to_b,
                          alignment.b_runs, a_block.run), 0)
        bits = ()
        if a_block and b_block and a_frames.count == b_frames.count:
            bits = _side_by_side(_runs_of_block(alignment.a_runs, a_block),
                                 _runs_of_block(alignment.b_runs, b_block), apart)
        found.append(Difference(a_frames, b_frames,
                                "replaced" if a_block and b_block else "removed" if a_block else "added",
                                bits))
    return found


def _runs_of_block(runs: list[Run], block: _Block) -> list[Run]:
    out, index = [], block.run
    while index < len(runs) and runs[index].start < block.frames.end:
        out.append(runs[index])
        index += 1
    return out


def compare_editions(db_path: str, edition_a: str, edition_b: str,
                     picture_hash: str = "block_mean_0",
                     with_averages: bool = False) -> list[Difference | Move]:
    """Everything to report between two editions of the one film, its links
    checked by the editions' block averages if asked."""
    a_frames = read_frames(db_path, edition_a, picture_hash)
    b_frames = read_frames(db_path, edition_b, picture_hash)
    averages = None
    if with_averages:
        from movie_edition_comparer.averages import read_averages
        averages = (read_averages(db_path, edition_a, len(a_frames)),
                    read_averages(db_path, edition_b, len(b_frames)))
    return compare_runs(runs_of(a_frames), runs_of(b_frames), averages)


# --- reporting ---------------------------------------------------------------

# Film on Blu-ray runs at 24000/1001 frames a second, exactly. Written out
# as a decimal it was 23.976216, eight parts in a million fast, which over a
# three-hour film puts a time worked out from a frame index two frames late.
fps = 24000 / 1001


def frame_to_time(frame: int) -> timedelta:
    return datetime.timedelta(seconds=frame / fps)


def clock(frame: int) -> str:
    """A frame's place in the film, as h:mm:ss.ss."""
    seconds = frame / fps
    return f"{int(seconds // 3600)}:{int(seconds % 3600 // 60):02d}:{seconds % 60:05.2f}"


def length(count: int) -> str:
    """A number of frames, and how long they last."""
    seconds = count / fps
    return f"{count} ({int(seconds // 60)}:{seconds % 60:05.2f})" if count else "0"


@dataclass(frozen=True)
class Row:
    """One thing reported, as the table and the JSON say it.

    Both sides are given by frame and by time, since the database and the
    frames cut from the video go by the one and a person goes by the other.
    """
    kind: str
    a: Frames
    b: Frames
    bits: tuple[tuple[int, int], ...] = ()

    @classmethod
    def of(cls, item: Difference | Move, same_picture_within: int | None = None) -> list["Row"]:
        """The rows for one thing reported: one, unless a line is drawn.

        Given how many bits apart is still the same picture, a re-encoding
        further apart than that is a replacement, and a replacement of the
        same length whose frames are within it is a re-encoding -- in
        stretches, where a stretch is some of each.
        """
        if isinstance(item, Move):
            return [cls("moved", Frames(item.a_start, item.count), Frames(item.b_start, item.count))]
        if same_picture_within is None or item.kind not in ("reencoded", "replaced") or not item.bits:
            return [cls(item.kind, item.a, item.b, item.bits)]
        rows, a_at, b_at = [], item.a.start, item.b.start
        for frames, apart in item.bits:
            kind = "reencoded" if apart <= same_picture_within else "replaced"
            if rows and rows[-1].kind == kind:
                last = rows[-1]
                rows[-1] = cls(kind, Frames(last.a.start, last.a.count + frames),
                               Frames(last.b.start, last.b.count + frames), last.bits + ((frames, apart),))
            else:
                rows.append(cls(kind, Frames(a_at, frames), Frames(b_at, frames), ((frames, apart),)))
            a_at += frames
            b_at += frames
        return rows

    @property
    def bits_apart(self) -> int | None:
        return max((apart for _, apart in self.bits), default=None)

    @property
    def size(self) -> int:
        return max(self.a.count, self.b.count)

    @staticmethod
    def span(frames: Frames) -> str:
        return f"{frames.start}–{frames.end - 1}" if frames.count else "—"

    def cells(self) -> tuple:
        return (self.kind,
                self.span(self.a), clock(self.a.start),
                self.span(self.b), clock(self.b.start),
                length(self.a.count), length(self.b.count),
                "—" if self.bits_apart is None else self.bits_apart)

    def record(self) -> dict:
        side = lambda frames: {"start": frames.start, "count": frames.count, "time": clock(frames.start)}
        return {"type": self.kind, "a": side(self.a), "b": side(self.b),
                "bits_apart": self.bits_apart, "bits": [list(stretch) for stretch in self.bits]}


HEADERS = ["Type", "A frames", "A at", "B frames", "B at", "A length", "B length", "Bits apart"]


def report(reported: list[Difference | Move], same_picture_within: int | None = None) -> list[Row]:
    """Everything reported as rows, smallest first, so what matters most is
    last on the screen. Given a number of bits, the line between the same
    picture and another is drawn there rather than where the comparison
    drew it."""
    rows = [row for item in reported for row in Row.of(item, same_picture_within)]
    return sorted(_folded(rows), key=lambda row: row.size)


def _folded(rows: list[Row]) -> list[Row]:
    """Rows of one kind that touch on both sides, run together.

    Drawing the line elsewhere than the comparison did can leave a
    replacement beside a re-encoding beside another replacement, all of
    one frame; where they are now the same kind they are one stretch.
    """
    out: list[Row] = []
    for row in sorted(rows, key=lambda row: (row.a.start, row.b.start)):
        last = out[-1] if out else None
        if (last and row.kind == last.kind and row.kind in ("reencoded", "replaced")
                and last.a.end == row.a.start and last.b.end == row.b.start
                and (row.kind == "reencoded" or (last.bits and row.bits))):
            out[-1] = Row(row.kind, Frames(last.a.start, last.a.count + row.a.count),
                          Frames(last.b.start, last.b.count + row.b.count), _stretches(last.bits + row.bits))
        else:
            out.append(row)
    return out


def configure_parser(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--db", required=True,
                        help="Path to the film's database, e.g. data/two_towers.db")
    parser.add_argument("--edition-a", required=True,
                        help="Name of the first edition, as it was hashed")
    parser.add_argument("--edition-b", required=True,
                        help="Name of the second edition, as it was hashed")
    parser.add_argument("--label-a", default=None,
                        help="What to call the first edition in output filenames (default: its name)")
    parser.add_argument("--label-b", default=None,
                        help="What to call the second edition in output filenames (default: its name)")
    parser.add_argument("--movie-a", default=None,
                        help="Path to the first edition's video, to cut clips and frames from")
    parser.add_argument("--movie-b", default=None,
                        help="Path to the second edition's video, to cut clips and frames from")
    parser.add_argument("--output-dir", default="out",
                        help="Where to put clips and frames (default: out)")
    parser.add_argument("--padding", type=float, default=5,
                        help="Seconds of footage to keep either side of a clip (default: 5)")
    parser.add_argument("--json", action="store_true",
                        help="Print what was reported as JSON as well, one record per row")
    parser.add_argument("--picture-hash", default="block_mean_0", choices=list(PICTURE_HASHES), metavar="HASH",
                        help="Which picture hash to go by: " + ", ".join(PICTURE_HASHES) + " (default: %(default)s)")
    parser.add_argument("--link-within", type=int, default=perceptual_match_threshold, metavar="BITS",
                        help="Picture hashes this many bits apart or fewer are the same picture when "
                             "the editions are lined up (default: %(default)s)")
    parser.add_argument("--same-picture-within", type=int, default=None, metavar="BITS",
                        help="Draw the line between re-encoded and replaced footage here in the report, "
                             "which may be tighter or looser than --link-within (default: the same)")
    parser.add_argument("--with-averages", action="store_true",
                        help="Check every link the picture hash makes by the frames' block averages "
                             "(strider average must have been run on both editions)")
    parser.add_argument("--by-averages", action="store_true",
                        help="Line the editions up by the frames' block averages alone, with no picture "
                             "hash; how far apart frames are is then given in hundredths of a grey level")
    parser.add_argument("--no-trim", action="store_true",
                        help="Do not copy out the stretches of video, even when both videos are given")
    parser.add_argument("--no-frames", action="store_true",
                        help="Do not extract frames, even when both videos are given")
    parser.add_argument("--clips", action="store_true",
                        help="Cut a clip of exactly the frames of each difference, re-encoded at 720p (slow)")


def run(args: argparse.Namespace) -> None:
    label_a = args.label_a or args.edition_a
    label_b = args.label_b or args.edition_b

    global perceptual_match_threshold
    perceptual_match_threshold = args.link_within

    print()
    if args.by_averages:
        from movie_edition_comparer import compare_averages
        reported = compare_averages.compare_editions(args.db, args.edition_a, args.edition_b)
    else:
        reported = compare_editions(args.db, args.edition_a, args.edition_b, args.picture_hash,
                                    with_averages=args.with_averages)
    rows = report(reported, args.same_picture_within)

    kinds = Counter(row.kind for row in rows)
    print(f"Count ({len(rows)}): " + ", ".join(
        f"{kinds[kind]} {kind}"
        for kind in ("added", "removed", "replaced", "reencoded", "retimed", "moved") if kinds[kind]))
    print()
    print(tabulate([row.cells() for row in rows], headers=HEADERS, tablefmt="github",
                   colalign=("left", "right", "right", "right", "right", "right", "right", "right")))

    if args.json:
        print(json.dumps([row.record() for row in rows]))

    if args.movie_a and args.movie_b:
        print()
        cut_differences(
            [(row.a, row.b) for row in rows],
            Source(args.movie_a, label_a, args.edition_a),
            Source(args.movie_b, label_b, args.edition_b),
            args.db, args.output_dir, args.padding, fps,
            trim=not args.no_trim, frames=not args.no_frames, clips=args.clips)


def main():
    parser = argparse.ArgumentParser(
        prog="strider compare",
        description="Report where two hashed editions of a film differ")
    configure_parser(parser)
    run(parser.parse_args())


if __name__ == "__main__":
    main()
