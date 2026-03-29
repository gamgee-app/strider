"""Core comparison logic for detecting differences between movie editions.

All functions in this module are pure (no DB or filesystem access), making
them straightforward to test with synthetic data.
"""

import cv2

from movie_edition_comparer.algorithms import deserialize
from movie_edition_comparer.models import (
    ComparisonConfig,
    DifferenceType,
    FrameHash,
    FrameMatch,
    FrameRange,
    HashFetcher,
    SceneDifference,
)


# ---------------------------------------------------------------------------
# Pure utility functions
# ---------------------------------------------------------------------------

def hamming_distance(hash_a: str, hash_b: str) -> float:
    """Compute the hamming distance between two hex-encoded hashes."""
    array_a = deserialize(hash_a)
    array_b = deserialize(hash_b)
    return cv2.norm(array_a, array_b, cv2.NORM_HAMMING)


def count_leading_matches(
    distances: list[float], threshold: float,
    gap_tolerance: int = 0, gap_max_distance: float = float("inf"),
) -> int:
    """Count how many values from the start are at or below the threshold,
    allowing up to gap_tolerance consecutive outliers if each is below
    gap_max_distance.

    An outlier run is only forgiven if a value at or below threshold follows.
    """
    matched = 0
    gap_run = 0

    for d in distances:
        if d <= threshold:
            # Good frame — accept it and any preceding outliers
            matched += gap_run + 1
            gap_run = 0
        elif d <= gap_max_distance and gap_run < gap_tolerance:
            # Outlier within tolerance — tentatively continue
            gap_run += 1
        else:
            # Outlier too far or too many in a row — stop
            break

    return matched


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

    gap_tol = config.boundary_gap_tolerance
    gap_max = config.boundary_gap_max_distance

    return (
        count_leading_matches(start_dists, threshold, gap_tol, gap_max),
        count_leading_matches(end_dists, threshold, gap_tol, gap_max),
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
    a_range = FrameRange(prev_match.a.index, curr_match.a.index)
    b_range = FrameRange(prev_match.b.index, curr_match.b.index)

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

    return SceneDifference(
        a_range=a_range,
        b_range=b_range,
        difference_type=diff_type,
        fps=config.fps,
        start_match=prev_match,
        end_match=curr_match,
        first_inner_a=a_hashes[0] if a_hashes else None,
        first_inner_b=b_hashes[0] if b_hashes else None,
        last_inner_a=a_hashes[-1] if a_hashes else None,
        last_inner_b=b_hashes[-1] if b_hashes else None,
    )


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
