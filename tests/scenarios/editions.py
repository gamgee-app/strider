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


@dataclass(frozen=True)
class Added:
    """Footage edition_b has and edition_a does not."""
    letters: str
    nth: int = 1


@dataclass(frozen=True)
class Gone:
    """Footage edition_a has and edition_b does not."""
    letters: str
    nth: int = 1


@dataclass(frozen=True)
class Replaced:
    """Footage of edition_a standing against footage of edition_b."""
    a: str
    b: str
    a_nth: int = 1
    b_nth: int = 1


@dataclass(frozen=True)
class Relocated:
    """Footage in both editions, in a different place in each."""
    letters: str
    nth: int = 1


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

def runs_of(edition: str) -> dict[tuple[str, int], tuple[int, int]]:
    """Each run of one letter, as {(letter, which run): (start, length)}.

    Two runs of the same letter are told apart by which comes first, so "the
    second run of b" is a thing that can be pointed at.
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


def accounts_for_every_frame(scenario, answer) -> list[str]:
    """Complaints about an answer, judged against the editions alone.

    A second opinion on what expected() worked out, using only what the two
    strings plainly say: footage one edition lacks, or holds a different number
    of times, must be reported exactly once; footage both editions hold the same
    way must not be reported at all.
    """
    a_runs = runs_of(scenario.edition_a)
    b_runs = runs_of(scenario.edition_b)
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
    expect: list
    """The differences between the two editions, said outright.

    Written as Added, Gone, Replaced and Relocated over the letters, so a
    scenario says what the answer is rather than leaving it to be worked out.
    Frame positions follow from the editions, and accounts_for_every_frame
    checks the whole of it back against them.
    """

    def _at(self, edition: str, letters: str, nth: int, where: str) -> int:
        """Where a run of letters sits, insisting it is somewhere definite."""
        found = [i for i in range(len(edition) - len(letters) + 1)
                 if edition[i:i + len(letters)] == letters]
        if not found:
            raise ValueError(
                f"{self.name!r}: {letters!r} is not in {where} ({edition!r}).")
        if nth > len(found):
            raise ValueError(
                f"{self.name!r}: {where} has {len(found)} run(s) of {letters!r}, "
                f"so there is no {nth}.")
        if len(found) > 1 and nth == 1 and self._ambiguous(letters, found):
            raise ValueError(
                f"{self.name!r}: {letters!r} appears {len(found)} times in "
                f"{where} ({edition!r}), so say which with nth=.")
        return found[nth - 1]

    @staticmethod
    def _ambiguous(letters, found) -> bool:
        return not all(b - a == 1 for a, b in zip(found, found[1:])) or len(letters) > 1

    def frames(self) -> tuple[list[str], list[str]]:
        """The two editions as frame hashes."""
        return ([frame_hash(L) for L in self.edition_a],
                [frame_hash(L) for L in self.edition_b])

    def _gap(self, letters: str, at: int, home: str, other: str) -> int:
        """Where footage the other edition does not have would have sat."""
        for step in range(at - 1, -1, -1):
            letter = home[step]
            if letter in other:
                return other.index(letter) + 1
        return 0

    def expected(self) -> list:
        a, b = self.edition_a, self.edition_b
        found = []
        for item in self.expect:
            if isinstance(item, Added):
                at = self._at(b, item.letters, item.nth, "edition_b")
                found.append(Difference(
                    Region(self._gap(item.letters, at, b, a), 0),
                    Region(at, len(item.letters))))
            elif isinstance(item, Gone):
                at = self._at(a, item.letters, item.nth, "edition_a")
                found.append(Difference(
                    Region(at, len(item.letters)),
                    Region(self._gap(item.letters, at, a, b), 0)))
            elif isinstance(item, Replaced):
                found.append(Difference(
                    Region(self._at(a, item.a, item.a_nth, "edition_a"), len(item.a)),
                    Region(self._at(b, item.b, item.b_nth, "edition_b"), len(item.b))))
            elif isinstance(item, Relocated):
                at = self._at(a, item.letters, item.nth, "edition_a")
                found.append(Moved(len(item.letters), at,
                                   self._at(b, item.letters, item.nth, "edition_b")))
            else:
                raise TypeError(f"{self.name!r}: {item!r} is not an expectation")
        return sorted(found, key=_position)


def _position(item):
    return item.at if isinstance(item, Moved) else item.a.at
