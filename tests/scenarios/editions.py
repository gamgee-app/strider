"""A language for describing two editions of a film.

An edition is a string of letters. Each letter is one frame of footage; the same
letter in both editions is the same frame.

    Scenario(name="a frame is dropped and another moves earlier",
             edition_a="abcde",
             edition_b="adbe")

That is the whole specification. What the tool ought to report is worked out by
comparing the two editions, so there is no second description of a scenario that
could disagree with the editions themselves.

Nothing here knows anything about any particular film, and nothing here knows
anything about how the comparison is implemented. These scenarios say what the
right answer is, not how anything arrives at it.
"""

import hashlib
import itertools
from collections import Counter
from dataclasses import dataclass

HASH_BYTES = 32  # 256 bits, as wide as the hashes the tool compares


def frame_hash(letter: str) -> str:
    """The hash of one frame. Every distinct letter is a distinct frame."""
    return hashlib.sha256(f"frame:{letter}".encode()).digest()[:HASH_BYTES].hex()


# --- what the tool should report --------------------------------------------

@dataclass(frozen=True)
class Region:
    """Differing frames on one side: how many, and where they start."""
    at: int
    frames: int

    def __str__(self) -> str:
        if self.frames == 0:
            return f"nothing at {self.at}"
        return f"{self.frames} frame{'s' if self.frames != 1 else ''} at {self.at}"


@dataclass(frozen=True)
class Difference:
    """A place where the two editions hold different footage."""
    a: Region
    b: Region

    def __str__(self) -> str:
        return f"edition_a: {str(self.a):<22} edition_b: {self.b}"


@dataclass(frozen=True)
class Moved:
    """Footage in both editions, in a different place in each.

    Says more than a Difference at each of the two positions would: it is the
    same footage relocated, not two unrelated regions that disagree.
    """
    frames: int
    at: int
    to: int

    def __str__(self) -> str:
        plural = "s" if self.frames != 1 else ""
        return (f"{self.frames} frame{plural} at {self.at} in edition_a "
                f"appear at {self.to} in edition_b")


def describe(reported) -> list[Difference]:
    """Turn (a_start, a_end, b_start, b_end) tuples into Differences.

    A comparer reports the matching frames either side of a difference, so the
    differing frames are the ones strictly between them.
    """
    return [
        Difference(Region(a0 + 1, max(0, a1 - a0 - 1)), Region(b0 + 1, max(0, b1 - b0 - 1)))
        for a0, a1, b0, b1 in reported
    ]


def satisfies(truth: list, reported: list) -> bool:
    return truth == reported


# --- scenarios ---------------------------------------------------------------

class Ambiguous(Exception):
    """The editions admit more than one equally good reading."""


def _stayed_put(common, a_at, b_at):
    """Which frames keep their order, and which moved.

    The frames that stayed put are the longest set whose order is the same in
    both editions. Raises where two such sets are equally long, because then
    which frames "moved" is a choice rather than a fact about the editions.

    Every subset is tried. Scenarios hold a handful of frames, so the simplest
    thing that is obviously right is the right thing.
    """
    order = sorted(common, key=lambda L: a_at[L])
    if len(order) > 16:
        raise ValueError(
            f"{len(order)} shared frames is too many to check every ordering. "
            f"Scenarios are meant to be small enough to read."
        )

    for size in range(len(order), 0, -1):
        same_order = [
            set(pick) for pick in itertools.combinations(order, size)
            if all(b_at[x] < b_at[y] for x, y in zip(pick, pick[1:]))
        ]
        if len(same_order) == 1:
            return same_order[0], set(common) - same_order[0]
        if same_order:
            raise Ambiguous
    return set(), set(common)


def accounts_for_every_frame(scenario, answer) -> list[str]:
    """Complaints about an answer, judged against the editions alone.

    A second opinion on what expected() worked out, using only what the two
    strings plainly say: footage one edition lacks, or holds a different number
    of times, must be reported exactly once; footage both editions hold the same
    way must not be reported at all.
    """
    a_runs = scenario._runs(scenario.edition_a)
    b_runs = scenario._runs(scenario.edition_b)
    shared = set(a_runs) & set(b_runs)
    same = {r for r in shared if a_runs[r][1] == b_runs[r][1]}

    def frames_of(runs, which):
        out = set()
        for run in which:
            at, length = runs[run]
            out |= set(range(at, at + length))
        return out

    complaints: list[str] = []
    reported, relocated = {"edition_a": [], "edition_b": []}, set()

    for item in answer:
        if isinstance(item, Moved):
            relocated |= set(range(item.at, item.at + item.frames))
        else:
            reported["edition_a"] += range(item.a.at, item.a.at + item.a.frames)
            reported["edition_b"] += range(item.b.at, item.b.at + item.b.frames)

    for side, runs, edition in (
        ("edition_a", a_runs, scenario.edition_a),
        ("edition_b", b_runs, scenario.edition_b),
    ):
        untouched = frames_of(runs, same)
        seen = reported[side]
        for index in range(len(edition)):
            times = seen.count(index)
            if index in untouched:
                if side == "edition_a" and index in relocated:
                    continue
                if times:
                    complaints.append(
                        f"{edition[index]} at {side} {index} is in both editions "
                        f"the same way, so it is not a difference, but it is "
                        f"reported as one")
            elif times != 1:
                complaints.append(
                    f"{edition[index]} at {side} {index} is not in both editions "
                    f"the same way, so it should be reported exactly once; it is "
                    f"reported {times} times")

    return complaints


@dataclass(frozen=True)
class Scenario:
    name: str
    story: str
    edition_a: str
    edition_b: str
    moved: str = ""
    """Which frames moved, where the editions do not say on their own.

    Reordering is the only thing two editions can be ambiguous about: when
    frames trade places, calling one of them the one that stayed put is a
    coin-flip. Naming the frames that moved settles that and nothing else --
    everything else is still worked out from the editions, and checked.
    """

    def _runs(self, edition: str) -> dict[tuple[str, int], tuple[int, int]]:
        """Each run of one letter, as {(letter, which run): (start, length)}.

        A letter may appear more than once. Repeated letters are frames that
        look exactly alike -- black frames, a held frame, a static shot. Two
        runs of the same letter are told apart by which comes first, so "the
        second run of b" is a thing a scenario can be about.
        """
        runs, seen, index = {}, Counter(), 0
        while index < len(edition):
            letter = edition[index]
            length = 1
            while index + length < len(edition) and edition[index + length] == letter:
                length += 1
            seen[letter] += 1
            runs[(letter, seen[letter])] = (index, length)
            index += length
        return runs

    def frames(self) -> tuple[list[str], list[str]]:
        """The two editions as frame hashes."""
        return ([frame_hash(L) for L in self.edition_a],
                [frame_hash(L) for L in self.edition_b])

    def _what_moved(self, common, a_at, b_at) -> set:
        try:
            settled = _stayed_put(common, a_at, b_at)[1]
        except Ambiguous:
            settled = None

        if not self.moved:
            if settled is None:
                raise ValueError(
                    f"{self.name!r}: more than one run of frames could be called "
                    f"the one that stayed put, so which frames moved is a choice. "
                    f"Name the frames that moved."
                )
            return settled

        moved = set()
        for letter in self.moved:
            runs = [r for r in common if r[0] == letter]
            if not runs:
                raise ValueError(
                    f"{self.name!r}: {letter!r} is said to have moved, but is not "
                    f"in both editions. Footage in only one edition has not "
                    f"moved -- one edition simply does not have it."
                )
            if len(runs) > 1:
                raise ValueError(
                    f"{self.name!r}: {letter!r} appears more than once, so saying "
                    f"it moved does not say which run moved."
                )
            moved.add(runs[0])

        order = sorted(common - moved, key=lambda r: a_at[r])
        if any(b_at[x] > b_at[y] for x, y in zip(order, order[1:])):
            raise ValueError(
                f"{self.name!r}: with {sorted(r[0] for r in moved)} moved, the "
                f"frames left over still do not keep their order, so this does "
                f"not settle what the editions are ambiguous about."
            )
        if settled is not None and settled != moved:
            raise ValueError(
                f"{self.name!r} names {sorted(r[0] for r in moved)} as the frames "
                f"that moved, but the editions are not ambiguous and say "
                f"{sorted(r[0] for r in settled)}. Name moved frames only where "
                f"the editions admit more than one reading."
            )
        return moved

    def expected(self) -> list:
        a_runs = self._runs(self.edition_a)
        b_runs = self._runs(self.edition_b)
        a_at = {r: at for r, (at, _) in a_runs.items()}
        b_at = {r: at for r, (at, _) in b_runs.items()}
        common = set(a_runs) & set(b_runs)

        moved = self._what_moved(common, a_at, b_at)
        for run in moved:
            if a_runs[run][1] != b_runs[run][1]:
                raise ValueError(
                    f"{self.name!r}: {run[0]!r} both moved and changed length. "
                    f"That is two things happening to one piece of footage; "
                    f"give them separate letters."
                )

        found = [Moved(a_runs[r][1], a_at[r], b_at[r]) for r in moved]

        # A run in both editions whose length changed is footage that is
        # partly there and partly not, wherever it sits.
        resized = {r for r in common - moved if a_runs[r][1] != b_runs[r][1]}
        for run in resized:
            found.append(Difference(Region(a_at[run], a_runs[run][1]),
                                    Region(b_at[run], b_runs[run][1])))

        # Walk the runs that stayed put and unchanged. Anything between two of
        # them that no move accounts for is footage one edition has and the
        # other does not.
        unchanged = common - moved - resized
        settled = common | resized

        def gap_after(runs, home, other_runs, other_at) -> int:
            first = min(home[r][0] for r in runs)
            earlier = [r for r in home if home[r][0] < first and r in other_runs]
            if not earlier:
                return 0
            nearest = max(earlier, key=lambda r: home[r][0])
            return other_at[nearest] + other_runs[nearest][1]

        def between(runs, lo, hi):
            return {r: v for r, v in runs.items()
                    if r not in settled and lo <= v[0] < hi}

        anchors = sorted(unchanged, key=lambda r: a_at[r])
        edges = [(-1, -1, 0, 0)] + [
            (a_at[r], b_at[r], a_runs[r][1], b_runs[r][1]) for r in anchors]
        for index, (a_here, b_here, a_len, b_len) in enumerate(edges):
            a_from = 0 if a_here < 0 else a_here + a_len
            b_from = 0 if b_here < 0 else b_here + b_len
            if index + 1 < len(edges):
                a_to, b_to = edges[index + 1][0], edges[index + 1][1]
            else:
                a_to, b_to = len(self.edition_a), len(self.edition_b)
            only_a = between(a_runs, a_from, a_to)
            only_b = between(b_runs, b_from, b_to)
            if not only_a and not only_b:
                continue
            side_a = (Region(min(v[0] for v in only_a.values()),
                             sum(v[1] for v in only_a.values())) if only_a
                      else Region(gap_after(only_b, b_runs, a_runs, a_at), 0))
            side_b = (Region(min(v[0] for v in only_b.values()),
                             sum(v[1] for v in only_b.values())) if only_b
                      else Region(gap_after(only_a, a_runs, b_runs, b_at), 0))
            found.append(Difference(side_a, side_b))

        return sorted(found, key=_position)


def _position(item):
    return item.at if isinstance(item, Moved) else item.a.at
