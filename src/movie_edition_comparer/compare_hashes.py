"""Hash comparison module for detecting differences between movie editions.

Compares frame hashes from two editions of a movie to identify scenes that are:
- Unique to one edition (added/removed content)
- Modified between editions (same scene, different frames)
- Reordered between editions (same frames, different sequence)
"""

import datetime
import json
import os.path
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import timedelta
from typing import Callable

import cv2
import ffmpeg
from progress.bar import Bar
from tabulate import tabulate

from algorithms import deserialize


@dataclass(frozen=True)
class ComparisonConfig:
    """Configuration parameters for hash comparison."""
    fps: float = 23.976216
    perceptual_match_threshold: float = 5.0
    extended_similarity_threshold: int = 12
    maximum_inter_match_search: int = 24


@dataclass(frozen=True)
class FrameHash:
    """A frame index paired with its hash value."""
    index: int
    hash: str


@dataclass(frozen=True)
class FrameMatch:
    """A pair of frames (one from each edition) with matching hashes."""
    a: FrameHash
    b: FrameHash


class DifferenceType:
    UNIQUE_TO_A = "unique_to_a"
    UNIQUE_TO_B = "unique_to_b"
    MODIFIED = "modified"
    REORDERED = "reordered"


@dataclass(frozen=True)
class TimeRange:
    """A time range within a video."""
    start: timedelta
    end: timedelta

    @property
    def duration(self) -> timedelta:
        return self.end - self.start


@dataclass(frozen=True)
class SceneDifference:
    """A detected difference between two movie editions."""
    a_range: TimeRange
    b_range: TimeRange
    difference_type: str

    @property
    def duration_difference(self) -> timedelta:
        return abs(self.b_range.duration - self.a_range.duration)


# Type alias: given (start_index_inclusive, end_index_exclusive), returns frame hashes
HashFetcher = Callable[[int, int], list[FrameHash]]


# ---------------------------------------------------------------------------
# Pure utility functions
# ---------------------------------------------------------------------------

def frame_to_time(frame: int, fps: float) -> timedelta:
    """Convert a frame index to a timestamp."""
    return timedelta(seconds=frame / fps)


def hamming_distance(hash_a: str, hash_b: str) -> float:
    """Compute the hamming distance between two hex-encoded hashes."""
    array_a = deserialize(hash_a)
    array_b = deserialize(hash_b)
    return cv2.norm(array_a, array_b, cv2.NORM_HAMMING)


def count_leading_matches(distances: list[float], threshold: float) -> int:
    """Count how many consecutive values from the start are at or below the threshold."""
    for i, d in enumerate(distances):
        if d > threshold:
            return i
    return len(distances)


# ---------------------------------------------------------------------------
# Ordering: longest increasing subsequence
# ---------------------------------------------------------------------------

def _lis_indices(values: list[int]) -> list[int]:
    """Return indices forming the longest strictly increasing subsequence.

    Uses patience sorting for O(n log n) performance.
    """
    if not values:
        return []

    n = len(values)
    # tails[i] = index in `values` of the smallest ending element
    #            for an increasing subsequence of length i+1
    tails: list[int] = []
    parent = [-1] * n

    for i in range(n):
        lo, hi = 0, len(tails)
        while lo < hi:
            mid = (lo + hi) // 2
            if values[tails[mid]] < values[i]:
                lo = mid + 1
            else:
                hi = mid

        if lo > 0:
            parent[i] = tails[lo - 1]

        if lo == len(tails):
            tails.append(i)
        else:
            tails[lo] = i

    # Reconstruct the subsequence
    result = []
    idx = tails[-1]
    while idx != -1:
        result.append(idx)
        idx = parent[idx]

    return list(reversed(result))


def filter_to_monotonic(
    matches: list[FrameMatch],
) -> tuple[list[FrameMatch], list[FrameMatch]]:
    """Given matches sorted by a.index, find the longest subsequence where
    b.index is strictly increasing.

    Returns (ordered_matches, removed_matches).  Removed matches represent
    frames that exist in both editions but in a different order.
    """
    if len(matches) <= 1:
        return list(matches), []

    b_values = [m.b.index for m in matches]
    lis_idx_set = set(_lis_indices(b_values))

    ordered = [m for i, m in enumerate(matches) if i in lis_idx_set]
    removed = [m for i, m in enumerate(matches) if i not in lis_idx_set]
    return ordered, removed


# ---------------------------------------------------------------------------
# Core comparison logic
# ---------------------------------------------------------------------------

def _frames_are_similar(
    hashes: list[FrameHash],
    prev_anchor: FrameHash,
    next_anchor: FrameHash,
    threshold: float,
) -> bool:
    """Check if all frames are perceptually similar to their surrounding anchor
    frames.  Used to filter out minor frame-rate or encoding differences that
    don't represent meaningful scene changes."""
    if not hashes:
        return True

    dists_to_prev = [hamming_distance(prev_anchor.hash, h.hash) for h in hashes]
    dists_to_next = [hamming_distance(next_anchor.hash, h.hash) for h in hashes]

    # Every frame must be close to at least one anchor
    return min(max(dists_to_prev), max(dists_to_next)) <= threshold


def _refine_boundaries(
    a_hashes: list[FrameHash],
    b_hashes: list[FrameHash],
    config: ComparisonConfig,
) -> tuple[int, int]:
    """Check how many frames at the start/end of a gap are perceptually
    identical between editions.

    Returns (start_matches, end_matches) — the number of frames to trim
    from each end of the gap.
    """
    max_search = config.maximum_inter_match_search
    threshold = config.perceptual_match_threshold

    a_start = [h.hash for h in a_hashes[:max_search]]
    b_start = [h.hash for h in b_hashes[:max_search]]
    a_end = [h.hash for h in a_hashes[-1:-1 - max_search:-1]]
    b_end = [h.hash for h in b_hashes[-1:-1 - max_search:-1]]

    start_dists = [hamming_distance(a, b) for a, b in zip(a_start, b_start)]
    end_dists = [hamming_distance(a, b) for a, b in zip(a_end, b_end)]

    return (
        count_leading_matches(start_dists, threshold),
        count_leading_matches(end_dists, threshold),
    )


def analyze_match_pair(
    prev_match: FrameMatch,
    curr_match: FrameMatch,
    a_fetcher: HashFetcher,
    b_fetcher: HashFetcher,
    removed_matches: list[FrameMatch],
    config: ComparisonConfig,
) -> SceneDifference | None:
    """Analyze the gap between two consecutive ordered matches to detect a
    scene difference.

    Returns None if the gap represents identical content or negligible
    frame-rate differences.
    """
    prev_lag = prev_match.b.index - prev_match.a.index
    curr_lag = curr_match.b.index - curr_match.a.index

    if curr_lag == prev_lag:
        return None

    a_gap_start = prev_match.a.index + 1
    a_gap_end = curr_match.a.index
    b_gap_start = prev_match.b.index + 1
    b_gap_end = curr_match.b.index

    a_frame_count = a_gap_end - a_gap_start
    b_frame_count = b_gap_end - b_gap_start

    if a_frame_count < 0 or b_frame_count < 0:
        return None

    a_hashes = a_fetcher(a_gap_start, a_gap_end)
    b_hashes = b_fetcher(b_gap_start, b_gap_end)

    # Filter out small runs of near-duplicate frames (encoding/framerate jitter)
    if a_frame_count == 0 and 0 < b_frame_count < config.extended_similarity_threshold:
        if _frames_are_similar(b_hashes, prev_match.b, curr_match.b, config.perceptual_match_threshold):
            return None

    if b_frame_count == 0 and 0 < a_frame_count < config.extended_similarity_threshold:
        if _frames_are_similar(a_hashes, prev_match.a, curr_match.a, config.perceptual_match_threshold):
            return None

    # Refine boundaries when both editions have frames in the gap
    if a_frame_count > 0 and b_frame_count > 0:
        start_trim, end_trim = _refine_boundaries(a_hashes, b_hashes, config)

        if start_trim > 0 or end_trim > 0:
            new_prev = prev_match
            new_curr = curr_match

            if start_trim > 0:
                new_prev = FrameMatch(
                    a_hashes[start_trim - 1],
                    b_hashes[start_trim - 1],
                )
            if end_trim > 0:
                new_curr = FrameMatch(
                    a_hashes[len(a_hashes) - end_trim],
                    b_hashes[len(b_hashes) - end_trim],
                )

            return analyze_match_pair(
                new_prev, new_curr,
                a_fetcher, b_fetcher,
                removed_matches, config,
            )

    # Classify the difference
    a_time_start = frame_to_time(prev_match.a.index, config.fps)
    a_time_end = frame_to_time(curr_match.a.index, config.fps)
    b_time_start = frame_to_time(prev_match.b.index, config.fps)
    b_time_end = frame_to_time(curr_match.b.index, config.fps)

    a_range = TimeRange(a_time_start, a_time_end)
    b_range = TimeRange(b_time_start, b_time_end)

    if a_frame_count == 0:
        diff_type = DifferenceType.UNIQUE_TO_B
    elif b_frame_count == 0:
        diff_type = DifferenceType.UNIQUE_TO_A
    else:
        # Check whether frames removed for ordering violations fall in this gap.
        # We only check the a-side range because removed matches have b indices
        # that are out of order by definition — they won't necessarily land in
        # the b-gap range.
        reordered_in_gap = [
            m for m in removed_matches
            if a_gap_start <= m.a.index < a_gap_end
        ]
        diff_type = DifferenceType.REORDERED if reordered_in_gap else DifferenceType.MODIFIED

    return SceneDifference(a_range, b_range, diff_type)


def find_all_differences(
    all_matches: list[FrameMatch],
    a_fetcher: HashFetcher,
    b_fetcher: HashFetcher,
    config: ComparisonConfig | None = None,
) -> list[SceneDifference]:
    """Find all scene differences between two movie editions.

    Args:
        all_matches: All unique frame matches between editions (any order).
        a_fetcher: Callable(start, end) returning FrameHash list for edition A.
        b_fetcher: Callable(start, end) returning FrameHash list for edition B.
        config: Comparison configuration.  Uses defaults if None.

    Returns:
        List of detected scene differences, ordered by timestamp.
    """
    if config is None:
        config = ComparisonConfig()

    sorted_matches = sorted(all_matches, key=lambda m: m.a.index)
    ordered_matches, removed_matches = filter_to_monotonic(sorted_matches)

    if len(ordered_matches) < 2:
        return []

    differences: list[SceneDifference] = []
    for i in range(len(ordered_matches) - 1):
        diff = analyze_match_pair(
            ordered_matches[i], ordered_matches[i + 1],
            a_fetcher, b_fetcher,
            removed_matches, config,
        )
        if diff is not None:
            differences.append(diff)

    return differences


# ---------------------------------------------------------------------------
# Database access layer
# ---------------------------------------------------------------------------

def read_hashes_from_db(
    db_path: str, table_name: str, start: int, end: int,
) -> list[FrameHash]:
    """Read frame hashes from the database for a given index range [start, end)."""
    with closing(sqlite3.connect(db_path)) as connection:
        cursor = connection.cursor()
        cursor.execute(
            f"SELECT frame_index, hash_block_mean_0 "
            f"FROM {table_name} "
            f"WHERE frame_index >= ? AND frame_index < ?",
            (start, end),
        )
        return [FrameHash(row[0], row[1]) for row in cursor.fetchall()]


def make_db_fetcher(db_path: str, table_name: str) -> HashFetcher:
    """Create a HashFetcher backed by a SQLite database."""
    def fetcher(start: int, end: int) -> list[FrameHash]:
        return read_hashes_from_db(db_path, table_name, start, end)
    return fetcher


def read_unique_matches(
    db_path: str, table_a: str, table_b: str,
) -> list[FrameMatch]:
    """Query all unique frame hash matches between two edition tables.

    A match is a hash value that appears exactly once in each edition.
    Unlike the old implementation, ordering is NOT filtered here — that
    is handled by filter_to_monotonic() so we can detect reordered scenes.
    """
    with closing(sqlite3.connect(db_path)) as connection:
        cursor = connection.cursor()
        cursor.execute(f"""
            WITH a_unique AS (
                    SELECT hash_block_mean_0 AS hash
                    FROM {table_a}
                    GROUP BY hash
                    HAVING count(1) = 1
                ),
                b_unique AS (
                    SELECT hash_block_mean_0 AS hash
                    FROM {table_b}
                    GROUP BY hash
                    HAVING count(1) = 1
                ),
                common AS (
                    SELECT hash FROM a_unique
                    INTERSECT
                    SELECT hash FROM b_unique
                )
            SELECT
                a.frame_index, a.hash_block_mean_0,
                b.frame_index, b.hash_block_mean_0
            FROM {table_a} a
            JOIN {table_b} b ON a.hash_block_mean_0 = b.hash_block_mean_0
            WHERE a.hash_block_mean_0 IN common
            ORDER BY a.frame_index
        """)
        return [
            FrameMatch(FrameHash(row[0], row[1]), FrameHash(row[2], row[3]))
            for row in cursor.fetchall()
        ]


# ---------------------------------------------------------------------------
# Video output helpers
# ---------------------------------------------------------------------------

def _time_to_filename(t: timedelta) -> str:
    return str(t).replace(":", ".")


def trim_video(
    input_file: str, identifier: str, index: int,
    start: timedelta, end: timedelta, output_dir: str,
) -> str:
    _, ext = os.path.splitext(input_file)
    filename = (
        f"{output_dir}/{index}-"
        f"{_time_to_filename(start)}-{_time_to_filename(end)}-"
        f"{identifier}{ext}"
    )
    if not os.path.isfile(filename):
        (
            ffmpeg
            .input(input_file)
            .output(filename, ss=start, to=end, c="copy")
            .run(quiet=True)
        )
    return filename


def grab_frame(
    input_file: str, identifier: str, index: int,
    timestamp: timedelta, output_dir: str,
):
    filename = f"{output_dir}/{index}-{_time_to_filename(timestamp)}-{identifier}.png"
    if not os.path.isfile(filename):
        (
            ffmpeg
            .input(input_file, ss=timestamp)
            .output(filename, vframes=1)
            .run(quiet=True)
        )


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main():
    db_path = "data/frame_hashes.db"

    label_a = "theatrical"
    table_a = "two_towers_theatrical"
    movie_a = (
        r"C:\Users\obroo\Lord of the Rings"
        r"\The Lord of the Rings The Two Towers (2002) Theatrical Remux-2160p HDR.mkv"
    )

    label_b = "extended"
    table_b = "two_towers_extended"
    movie_b = (
        r"C:\Users\obroo\Lord of the Rings"
        r"\The Lord of the Rings The Two Towers (2002) Extended Remux-2160p HDR.mkv"
    )

    output_dir = "out"
    print_json = False
    trim_videos = True
    grab_frames = True
    video_padding_seconds = 5
    config = ComparisonConfig()

    print("Reading unique matches…")
    all_matches = read_unique_matches(db_path, table_a, table_b)
    a_fetcher = make_db_fetcher(db_path, table_a)
    b_fetcher = make_db_fetcher(db_path, table_b)

    print("Finding differences…")
    differences = find_all_differences(all_matches, a_fetcher, b_fetcher, config)

    def sort_key(d: SceneDifference) -> timedelta:
        return max(d.a_range.duration, d.b_range.duration)

    sorted_diffs = sorted(differences, key=sort_key)

    tabulated = tabulate(
        [(
            d.a_range.start, d.a_range.end, d.difference_type,
            d.b_range.start, d.b_range.end, d.difference_type,
            d.a_range.duration, d.b_range.duration, d.duration_difference,
        ) for d in sorted_diffs],
        headers=[
            "A Start", "A End", "A Type",
            "B Start", "B End", "B Type",
            "A Duration", "B Duration", "Duration Diff",
        ],
        tablefmt="github",
    )

    print()
    print(f"Count ({len(sorted_diffs)}):")
    print()
    print(tabulated)

    if print_json:
        for label, attr in [("a", "a_range"), ("b", "b_range")]:
            ranges = [
                {
                    "start_time": str(getattr(d, attr).start),
                    "end_time": str(getattr(d, attr).end),
                    "type": d.difference_type,
                }
                for d in differences
                if getattr(d, attr).duration > timedelta(0)
            ]
            print(json.dumps(ranges))

    if trim_videos or grab_frames:
        print()
        video_padding = timedelta(seconds=video_padding_seconds)
        with Bar("Cutting", max=len(sorted_diffs)) as bar:
            for index, diff in enumerate(sorted_diffs):
                if trim_videos:
                    trim_video(movie_a, label_a, index,
                               diff.a_range.start - video_padding,
                               diff.a_range.start, output_dir)
                    trim_video(movie_a, label_a, index,
                               diff.a_range.end - diff.a_range.duration,
                               diff.a_range.end + video_padding, output_dir)
                    trim_video(movie_b, label_b, index,
                               diff.b_range.start - video_padding,
                               diff.b_range.end + video_padding, output_dir)

                if grab_frames:
                    grab_frame(movie_a, label_a, index, diff.a_range.start, output_dir)
                    grab_frame(movie_b, label_b, index, diff.b_range.start, output_dir)
                    grab_frame(movie_a, label_a, index, diff.a_range.end, output_dir)
                    grab_frame(movie_b, label_b, index, diff.b_range.end, output_dir)

                bar.next()


if __name__ == "__main__":
    main()
