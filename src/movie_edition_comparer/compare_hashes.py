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

import bisect
import datetime
import itertools
import json
import os.path
import sqlite3
from collections import Counter, defaultdict
from contextlib import closing
from dataclasses import dataclass
from datetime import timedelta

import cv2
import ffmpeg
from progress.bar import Bar
from tabulate import tabulate

from algorithms import deserialize


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

    @property
    def end(self) -> int:
        return self.start + self.count


@dataclass(frozen=True)
class Frames:
    """A stretch of frames on one side: how many, and where they start."""
    start: int
    count: int

    def __str__(self) -> str:
        if self.count == 0:
            return f"nothing at {self.start}"
        return f"{self.count} frame{'s' if self.count != 1 else ''} at {self.start}"


@dataclass(frozen=True)
class Difference:
    """A place where the two editions hold different footage."""
    a: Frames
    b: Frames

    def __str__(self) -> str:
        return f"edition_a: {str(self.a):<22} edition_b: {self.b}"


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


def read_frames(db_path: str, table_name: str) -> list[Frame]:
    with closing(sqlite3.connect(db_path)) as connection:
        cursor = connection.cursor()
        cursor.execute(f"""
            SELECT
                frame_index,
                hash_md5,
                hash_block_mean_0
            FROM
                {table_name}
            ORDER BY
                frame_index
        """)
        return [Frame(*row) for row in cursor.fetchall()]


def runs_of(frames: list[Frame]) -> list[Run]:
    """Frames gathered into runs of the same frame repeated."""
    runs: list[Run] = []
    for frame in frames:
        if runs and runs[-1].data_hash == frame.data_hash and runs[-1].end == frame.index:
            runs[-1].count += 1
        else:
            runs.append(Run(frame.index, 1, frame.data_hash, frame.picture_hash))
    return runs


def hamming_distance(hash_a: str, hash_b: str) -> float:
    array_a = deserialize(hash_a)
    array_b = deserialize(hash_b)
    return cv2.norm(array_a, array_b, cv2.NORM_HAMMING)


def same_frame(a: Run, b: Run) -> bool:
    """The same frame: the very same pixels."""
    return a.data_hash == b.data_hash


def same_picture(a: Run, b: Run) -> bool:
    """The same picture, however its pixels were arrived at."""
    return (a.picture_hash == b.picture_hash
            or hamming_distance(a.picture_hash, b.picture_hash) <= perceptual_match_threshold)


class Alignment:
    """Which run of edition_a is which run of edition_b."""

    def __init__(self, a_runs: list[Run], b_runs: list[Run]):
        self.a_runs = a_runs
        self.b_runs = b_runs
        self.a_to_b: dict[int, int] = {}
        self.b_to_a: dict[int, int] = {}

    def link(self, a_index: int, b_index: int) -> None:
        self.a_to_b[a_index] = b_index
        self.b_to_a[b_index] = a_index

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


def _pieces(picture_hash: str) -> list[str]:
    """The hash cut into more pieces than a match is allowed to differ by bits.

    Two hashes close enough to be one picture have a piece in common, since
    there are more pieces than bits they may differ by. Looking only at runs
    sharing a piece finds every match without reading every pair.
    """
    size = -(-len(picture_hash) // (perceptual_match_threshold + 1))
    return [f"{place}:{picture_hash[place:place + size]}"
            for place in range(0, len(picture_hash), size)]


def _link_alike(alignment: Alignment) -> None:
    """Link runs that look like one run on the other side and no other.

    What is left once equal hashes have been used up: two renderings of one
    picture that are a bit apart to look at as well.
    """
    sharing = defaultdict(list)
    for b_index in alignment.b_free():
        for piece in _pieces(alignment.b_runs[b_index].picture_hash):
            sharing[piece].append(b_index)

    alike = {}
    for a_index in alignment.a_free():
        nearby = {b_index
                  for piece in _pieces(alignment.a_runs[a_index].picture_hash)
                  for b_index in sharing.get(piece, ())}
        alike[a_index] = sorted(
            b_index for b_index in nearby
            if same_picture(alignment.a_runs[a_index], alignment.b_runs[b_index]))

    wanted = Counter(j for candidates in alike.values() for j in candidates)
    for a_index, candidates in alike.items():
        if len(candidates) == 1 and wanted[candidates[0]] == 1:
            alignment.link(a_index, candidates[0])


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


def _moves(alignment: Alignment, moved: set[int]) -> list[Move]:
    """Footage that moved, with runs that travelled together reported as one."""
    moves: list[Move] = []
    previous = None
    for a_index in sorted(moved):
        b_index = alignment.a_to_b[a_index]
        a_run, b_run = alignment.a_runs[a_index], alignment.b_runs[b_index]
        if previous == (a_index - 1, b_index - 1):
            moves[-1] = Move(moves[-1].count + a_run.count,
                             moves[-1].a_start, moves[-1].b_start)
        else:
            moves.append(Move(a_run.count, a_run.start, b_run.start))
        previous = (a_index, b_index)
    return moves


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


def _difference_of(a: Run, b: Run) -> Difference | None:
    """What to report of two runs that hold the same picture.

    Nothing, if they are the same frame for the same length of time. The
    picture being the same is not enough: a re-encoding is footage the two
    editions do not hold identically, and so is footage held longer.
    """
    if same_frame(a, b) and a.count == b.count:
        return None
    return Difference(Frames(a.start, a.count), Frames(b.start, b.count))


def _at(item: Difference | Move) -> int:
    return item.a_start if isinstance(item, Move) else item.a.start


def compare_runs(a_runs: list[Run], b_runs: list[Run]) -> list[Difference | Move]:
    """Everything to report between two editions, in the order it comes."""
    alignment = align(a_runs, b_runs)
    moved = _moved_runs(alignment)
    anchors = [(i, j) for i, j in alignment.pairs() if i not in moved]
    fences = [(-1, -1)] + anchors + [(len(a_runs), len(b_runs))]

    found: list[Difference | Move] = []
    for left, right in zip(fences, fences[1:]):
        found += _between(alignment, left, right)
        if right[0] < len(a_runs):
            difference = _difference_of(a_runs[right[0]], b_runs[right[1]])
            if difference:
                found.append(difference)
    found += _moves(alignment, moved)
    return sorted(found, key=_at)


def _between(alignment: Alignment,
             left: tuple[int, int], right: tuple[int, int]) -> list[Difference]:
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
        found.append(Difference(a_frames, b_frames))
    return found


def compare_editions(db_path: str, table_a_name: str,
                     table_b_name: str) -> list[Difference | Move]:
    """Everything to report between two editions held in the one database."""
    return compare_runs(runs_of(read_frames(db_path, table_a_name)),
                        runs_of(read_frames(db_path, table_b_name)))


# --- reporting ---------------------------------------------------------------

def frame_to_time(frame: int) -> timedelta:
    return datetime.timedelta(seconds=frame / fps)


def get_filename_time(time: timedelta) -> str:
    return str(time).replace(":", ".")


def trim_video(input_file: str, identifier: str, index: int, start: timedelta, end: timedelta) -> str:
    _, input_file_extension = os.path.splitext(input_file)
    filename = f"{output_dir}/{index}-{get_filename_time(start)}-{get_filename_time(end)}-{identifier}{input_file_extension}"
    if not os.path.isfile(filename):
        (
            ffmpeg
            .input(input_file)
            .output(filename, ss=start, to=end, c="copy")
            .run(quiet=True)
        )
    return filename


def grab_frame(input_file: str, identifier: str, index: int, timestamp: timedelta):
    filename = f"{output_dir}/{index}-{get_filename_time(timestamp)}-{identifier}.png"
    if not os.path.isfile(filename):
        (
            ffmpeg
            .input(input_file, ss=timestamp)
            .output(filename, vframes=1)
            .run(quiet=True)
        )


@dataclass
class TimeRange:
    start: timedelta
    end: timedelta
    range: timedelta
    type: str


def time_range(frames: Frames, other: Frames) -> TimeRange:
    return TimeRange(frame_to_time(frames.start),
                     frame_to_time(frames.start + max(0, frames.count - 1)),
                     frame_to_time(frames.count),
                     "new" if other.count == 0 else "different")


def get_differences_dict(hash_range: TimeRange):
    return {
        "start_time": str(hash_range.start),
        "end_time": str(hash_range.end),
        "type": hash_range.type
    }


fps = 23.976216
output_dir = "out"
perceptual_match_threshold = 5 # when comparing perceptual hashes, anything below this hamming distance will be considered a match


def main():
    db_path = "data/frame_hashes.db"

    label_a = "theatrical"
    table_a_name = "two_towers_theatrical"
    movie_a_filename = "C:\\Users\\obroo\\Lord of the Rings\\The Lord of the Rings The Two Towers (2002) Theatrical Remux-2160p HDR.mkv"

    label_b = "extended"
    table_b_name = "two_towers_extended"
    movie_b_filename = "C:\\Users\\obroo\\Lord of the Rings\\The Lord of the Rings The Two Towers (2002) Extended Remux-2160p HDR.mkv"

    print_json = False
    trim_videos = True
    grab_frames = True
    video_padding_seconds = 5

    print()
    reported = compare_editions(db_path, table_a_name, table_b_name)

    moves = [item for item in reported if isinstance(item, Move)]
    table = [(time_range(item.a, item.b), time_range(item.b, item.a))
             for item in reported if isinstance(item, Difference)]

    def sort_key(row: tuple[TimeRange, TimeRange]) -> timedelta:
        return max(row[0].range, row[1].range)

    sorted_table = sorted(table, key=sort_key)

    tabulated = tabulate(
        [(
            a.start, a.end, a.type,
            b.start, b.end, b.type,
            a.range, b.range, abs(b.range - a.range)
        ) for a, b in sorted_table],
        headers=["A Start", "A End", "A Type", "B Start", "B End", "B Type", "A Range", "B Range", "Range Difference"],
        tablefmt="github")

    print()
    print(f'Count ({len(sorted_table)}):')
    print()
    print(tabulated)

    if moves:
        print()
        print(f'Moved ({len(moves)}):')
        print()
        for move in moves:
            print(f"  {frame_to_time(move.a_start)} -> {frame_to_time(move.b_start)}"
                  f"  ({frame_to_time(move.count)})")

    if print_json:
        print(json.dumps([get_differences_dict(a) for a, b in table if a.range > timedelta(seconds=0)]))
        print(json.dumps([get_differences_dict(b) for a, b in table if b.range > timedelta(seconds=0)]))

    if trim_videos or grab_frames:
        print()
        with Bar('Cutting', max=len(sorted_table)) as bar:
            video_padding = timedelta(seconds=video_padding_seconds)
            for (index, (a, b)) in enumerate(sorted_table):

                if trim_videos:
                    trim_video(movie_a_filename, label_a, index, a.start - video_padding, a.start)
                    trim_video(movie_a_filename, label_a, index, a.end - a.range, a.end + video_padding)
                    trim_video(movie_b_filename, label_b, index, b.start - video_padding, b.end + video_padding)

                if grab_frames:
                    grab_frame(movie_a_filename, label_a, index, a.start)
                    grab_frame(movie_b_filename, label_b, index, b.start)
                    grab_frame(movie_a_filename, label_a, index, a.end)
                    grab_frame(movie_b_filename, label_b, index, b.end)

                bar.next()


if __name__ == "__main__":
    main()
