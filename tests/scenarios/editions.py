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
from dataclasses import dataclass, field

HASH_BYTES = 32  # 256 bits, as wide as the hashes the tool compares

RESEMBLES_WITHIN = 1
"""How many bits apart a primed frame sits from the frame it resembles.

One bit is the least two different frames can differ by, which makes it the
hardest case to tell apart and the only one that does not assume something
about how close is close enough. Any larger number would quietly settle for
being confusable with some tolerances and not others.
"""


def tokens(edition: str) -> list[str]:
    """An edition as frames. A frame is a letter, its case, and any primes.

    The same token is the same frame, always. Two tokens sharing a letter are
    two renderings of one picture:

        A and a     one picture, encoded twice -- the pixels differ, the
                    picture does not
        a and a'    the same, and a bit apart to look at as well
        A' and a'   that rendering a bit apart, encoded twice: they look
                    exactly alike, and their pixels differ

    So a' is a bit away from a, and A' is a' encoded again -- the same bits
    away from a as a', which is what makes it A' and not a''.
    """
    frames: list[str] = []
    for character in edition:
        if character == "'":
            if not frames:
                raise ValueError(f"{edition!r} starts with a prime, which follows nothing")
            frames[-1] += "'"
        else:
            frames.append(character)
    return frames


def picture(frame: str) -> str:
    """Which picture a frame is a rendering of."""
    return frame.rstrip("'").lower()


def data_hash(frame: str) -> str:
    """What the pixels are. Equal only between frames that are the same frame."""
    return hashlib.md5(f"pixels:{frame}".encode()).hexdigest()


def frame_hash(frame: str) -> str:
    """What the frame looks like.

    Two renderings of one picture look the same, however far apart their
    pixels are; each prime moves them one bit apart, the same bit for a'
    and A', which are the one rendering encoded twice.
    """
    raw = bytearray(hashlib.sha256(f"picture:{picture(frame)}".encode()).digest()[:HASH_BYTES])
    steps = frame.count("'")
    if steps:
        chooser = hashlib.sha256(f"step:{frame.lower()}".encode()).digest()
        order = sorted(range(HASH_BYTES * 8), key=lambda bit: chooser[bit % 32] ^ bit)
        for bit in order[:steps * RESEMBLES_WITHIN]:
            raw[bit // 8] ^= 1 << (bit % 8)
    return raw.hex()


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
    """A place where the two editions hold different footage, and how:
    added, removed, replaced, reencoded or retimed."""
    a: Region
    b: Region
    kind: str

    def __str__(self) -> str:
        return f"{self.kind:<10} edition_a: {str(self.a):<22} edition_b: {self.b}"


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
    """Footage the second edition has and the first does not."""
    letters: str
    nth: int = 0


@dataclass(frozen=True)
class Removed:
    """Footage the first edition has and the second does not."""
    letters: str
    nth: int = 0


@dataclass(frozen=True)
class Replaced:
    """Footage gone, and other footage standing where it was.

    Only for footage that is a different picture. Where the picture is the
    same and only its rendering or its count has changed, nothing has been
    replaced -- that is SamePicture.
    """
    a: str
    b: str
    a_nth: int = 0
    b_nth: int = 0


@dataclass(frozen=True)
class Reencoded:
    """One picture on both sides, carried by different frames.

    Encoded again, or a bit apart to look at. The footage has not been
    replaced by anything and lasts as long as it did; the frames carrying it
    are not the same frames.
    """
    a: str
    b: str
    a_nth: int = 0
    b_nth: int = 0


@dataclass(frozen=True)
class Retimed:
    """One picture on both sides, lasting a different number of frames."""
    a: str
    b: str
    a_nth: int = 0
    b_nth: int = 0


@dataclass(frozen=True)
class Relocated:
    """Footage in both editions, in a different place in each.

    `becomes` names how the footage is written where it turns up, for footage
    that is re-encoded on the way. The picture has to be the same one, since
    that is what makes it the same footage having moved rather than one piece
    going and another arriving.
    """
    letters: str
    nth: int = 0
    becomes: str = ""


def describe(reported) -> list:
    """Turn (a_start, a_end, b_start, b_end, kind) tuples into Differences.

    A comparer reports the matching frames either side of a difference, so the
    differing frames are the ones strictly between them. Footage a comparer
    says has moved arrives as a Moved, which says where it went rather than
    which frames it sits between, and passes through as it is.
    """
    return [
        item if isinstance(item, Moved) else
        Difference(Region(item[0] + 1, max(0, item[1] - item[0] - 1)),
                   Region(item[2] + 1, max(0, item[3] - item[2] - 1)), item[4])
        for item in reported
    ]


def satisfies(truth: list, reported: list) -> bool:
    return truth == reported


# --- scenarios ---------------------------------------------------------------

def runs_of(edition: str) -> dict[tuple[str, int], tuple[int, int]]:
    """Each run of one letter, as {(letter, which run): (start, length)}.

    Two runs of the same letter are told apart by which comes first, so "the
    second run of b" is a thing that can be pointed at.
    """
    frames = tokens(edition)
    runs, seen, index = {}, Counter(), 0
    while index < len(frames):
        letter = frames[index]
        length = 1
        while index + length < len(frames) and frames[index + length] == letter:
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
    reported = {"edition_a": [], "edition_b": []}
    relocated = {"edition_a": set(), "edition_b": set()}
    lengths = {"edition_a": len(tokens(scenario.edition_a)),
               "edition_b": len(tokens(scenario.edition_b))}

    for item in answer:
        if isinstance(item, Moved):
            for side, at in (("edition_a", item.at), ("edition_b", item.to)):
                if at + item.frames > lengths[side]:
                    complaints.append(
                        f"{item.frames} frame(s) at edition_a {item.at} are said to "
                        f"appear at edition_b {item.to}, which runs off the end of "
                        f"{side}, which has {lengths[side]}")
            relocated["edition_a"] |= set(range(item.at, item.at + item.frames))
            relocated["edition_b"] |= set(range(item.to, item.to + item.frames))
        else:
            reported["edition_a"] += range(item.a.at, item.a.at + item.a.frames)
            reported["edition_b"] += range(item.b.at, item.b.at + item.b.frames)

    for side, runs, edition in (
        ("edition_a", a_runs, tokens(scenario.edition_a)),
        ("edition_b", b_runs, tokens(scenario.edition_b)),
    ):
        untouched = frames_of(runs, same)
        seen = reported[side]
        for index in range(len(edition)):
            times = seen.count(index)
            if index in relocated[side]:
                if times:
                    complaints.append(
                        f"{edition[index]} at {side} {index} is reported as "
                        f"having moved, and as a difference as well")
                continue
            if index in untouched:
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
class Case:
    """One pair of editions exercising a scenario, and what it should report."""
    edition_a: str
    edition_b: str
    expect: list
    note: str = ""


@dataclass(frozen=True)
class Scenario:
    name: str
    story: str
    edition_a: str = ""
    edition_b: str = ""
    expect: list = field(default_factory=list)
    cases: list = field(default_factory=list)
    """The differences between the two editions, said outright.

    Written as Added, Gone, Replaced and Relocated over the letters, so a
    scenario says what the answer is rather than leaving it to be worked out.
    Frame positions follow from the editions, and accounts_for_every_frame
    checks the whole of it back against them.
    """

    def _check_primes_have_a_referent(self) -> None:
        """A primed frame is named after another frame, which has to exist.

        b' means "not b, but looks like b". If no b appears in either edition
        there is nothing for it to look like, and the name says nothing. B'
        means "b', encoded again", so it is b' that has to be there.
        """
        present = set(tokens(self.edition_a)) | set(tokens(self.edition_b))
        for frame in sorted(present):
            base = frame.rstrip("'")
            if base == frame:
                continue
            referents = [frame.lower()] if base.isupper() else [base, base.upper()]
            if not any(referent in present for referent in referents):
                raise ValueError(
                    f"{self.name!r}: {frame!r} is named after {referents[0]!r}, which is "
                    f"in neither edition. A frame can only be said to look like "
                    f"a frame that is there."
                )

    def _at(self, edition: str, letters: str, nth: int, where: str) -> int:
        """Where a run of letters sits, insisting it is somewhere definite.

        An nth of nought is nobody having said which, which will do only where
        there is nothing to choose between. Saying nth=1 is saying which, so it
        names the first of several where leaving it out would not.
        """
        frames, wanted = tokens(edition), tokens(letters)
        found = [i for i in range(len(frames) - len(wanted) + 1)
                 if frames[i:i + len(wanted)] == wanted]
        if not found:
            raise ValueError(
                f"{self.name!r}: {letters!r} is not in {where} ({edition!r}).")
        if nth == 0:
            if len(found) > 1 and self._ambiguous(wanted, found):
                raise ValueError(
                    f"{self.name!r}: {letters!r} appears {len(found)} times in "
                    f"{where} ({edition!r}), so say which with nth=.")
            nth = 1
        if nth > len(found):
            raise ValueError(
                f"{self.name!r}: {where} has {len(found)} run(s) of {letters!r}, "
                f"so there is no {nth}.")
        return found[nth - 1]

    @staticmethod
    def _ambiguous(letters, found) -> bool:
        return not all(b - a == 1 for a, b in zip(found, found[1:])) or len(letters) > 1

    def frames(self) -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
        """The two editions, each frame as (what its pixels are, what it looks like)."""
        return ([(data_hash(f), frame_hash(f)) for f in tokens(self.edition_a)],
                [(data_hash(f), frame_hash(f)) for f in tokens(self.edition_b)])

    def _gap(self, letters: str, at: int, home: str, other: str) -> int:
        """Where footage the other edition does not have would have sat."""
        home_pictures = [picture(f) for f in tokens(home)]
        other_pictures = [picture(f) for f in tokens(other)]
        for step in range(at - 1, -1, -1):
            if home_pictures[step] in other_pictures:
                return other_pictures.index(home_pictures[step]) + 1
        return 0

    def expected(self) -> list:
        self._check_primes_have_a_referent()
        a, b = self.edition_a, self.edition_b
        found = []
        for item in self.expect:
            if isinstance(item, Added):
                at = self._at(b, item.letters, item.nth, "edition_b")
                found.append(Difference(
                    Region(self._gap(item.letters, at, b, a), 0),
                    Region(at, len(tokens(item.letters))), "added"))
            elif isinstance(item, Removed):
                at = self._at(a, item.letters, item.nth, "edition_a")
                found.append(Difference(
                    Region(at, len(tokens(item.letters))),
                    Region(self._gap(item.letters, at, a, b), 0), "removed"))
            elif isinstance(item, (Replaced, Reencoded, Retimed)):
                left, right = tokens(item.a), tokens(item.b)
                here = {picture(f) for f in left}
                there = {picture(f) for f in right}
                kind = type(item).__name__
                if isinstance(item, Replaced) and here & there:
                    raise ValueError(
                        f"{self.name!r}: Replaced({item.a!r}, {item.b!r}) names "
                        f"{sorted(here & there)} on both sides. A picture is not "
                        f"replaced by itself -- say Reencoded or Retimed.")
                if not isinstance(item, Replaced) and here != there:
                    raise ValueError(
                        f"{self.name!r}: {kind}({item.a!r}, {item.b!r}) names "
                        f"{sorted(here)} against {sorted(there)}. Those are not "
                        f"the same picture -- say Replaced.")
                if isinstance(item, Reencoded) and len(left) != len(right):
                    raise ValueError(
                        f"{self.name!r}: Reencoded({item.a!r}, {item.b!r}) is "
                        f"{len(left)} frames against {len(right)}. Footage that "
                        f"lasts a different length has been retimed.")
                if isinstance(item, Retimed) and len(left) == len(right):
                    raise ValueError(
                        f"{self.name!r}: Retimed({item.a!r}, {item.b!r}) is "
                        f"{len(left)} frames on both sides, so nothing was "
                        f"retimed -- say Reencoded.")
                found.append(Difference(
                    Region(self._at(a, item.a, item.a_nth, "edition_a"), len(tokens(item.a))),
                    Region(self._at(b, item.b, item.b_nth, "edition_b"), len(tokens(item.b))),
                    kind.lower()))
            elif isinstance(item, Relocated):
                arrives = item.becomes or item.letters
                here = [picture(f) for f in tokens(item.letters)]
                there = [picture(f) for f in tokens(arrives)]
                if here != there:
                    raise ValueError(
                        f"{self.name!r}: {item.letters!r} cannot move and arrive "
                        f"as {arrives!r} -- they are not the same picture, so "
                        f"nothing moved.")
                at = self._at(a, item.letters, item.nth, "edition_a")
                found.append(Moved(len(tokens(item.letters)), at,
                                   self._at(b, arrives, item.nth, "edition_b")))
            else:
                raise TypeError(f"{self.name!r}: {item!r} is not an expectation")
        return sorted(found, key=_position)


def _position(item):
    return item.at if isinstance(item, Moved) else item.a.at


def cases_of(catalogue) -> list[tuple[str, str, "Scenario"]]:
    """Every case in the catalogue, as (scenario name, case note, a Scenario).

    A scenario groups the cases that exercise one property. Each is turned
    into a Scenario of its own so everything downstream works on one shape.
    """
    out = []
    for scenario in catalogue:
        for case in scenario.cases:
            out.append((
                scenario.name,
                case.note,
                Scenario(name=f"{scenario.name}: {case.note}" if case.note else scenario.name,
                         story=scenario.story,
                         edition_a=case.edition_a,
                         edition_b=case.edition_b,
                         expect=case.expect),
            ))
    return out
