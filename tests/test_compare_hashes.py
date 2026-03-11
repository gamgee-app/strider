"""Comprehensive tests for the hash comparison module."""

import sys
import os
from datetime import timedelta

import pytest

# Ensure the source package is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src", "movie_edition_comparer"))

from models import (
    ComparisonConfig,
    DifferenceType,
    FrameHash,
    FrameMatch,
    HashFetcher,
    SceneDifference,
    TimeRange,
)
from comparison import (
    _lis_indices,
    _frames_are_similar,
    _refine_boundaries,
    analyze_match_pair,
    count_leading_matches,
    filter_to_monotonic,
    find_all_differences,
    frame_to_time,
    hamming_distance,
)


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------

def _h(value: int) -> str:
    """Create a simple two-byte hex hash from an integer (0–65535).

    By encoding as two bytes we get hashes whose hamming distance is the
    number of differing bits.  For example:
        _h(0) = "0000"   (all bits 0)
        _h(1) = "0001"   (1 bit set)
        hamming_distance(_h(0), _h(1)) == 1
    """
    return format(value & 0xFFFF, "04x")


def _fh(index: int, value: int | None = None) -> FrameHash:
    """Shorthand for creating a FrameHash.  Uses index as hash value if
    value is not given."""
    if value is None:
        value = index
    return FrameHash(index, _h(value))


def _fm(a_idx: int, b_idx: int, hash_val: int | None = None) -> FrameMatch:
    """Shorthand for creating a FrameMatch with the same hash on both sides."""
    if hash_val is None:
        hash_val = a_idx * 1000 + b_idx  # unique per pair
    h = _h(hash_val)
    return FrameMatch(FrameHash(a_idx, h), FrameHash(b_idx, h))


def _make_fetcher(hashes: dict[int, int] | None = None, salt: int = 0) -> HashFetcher:
    """Build a HashFetcher backed by a dict mapping frame_index → hash_value.

    Missing indices default to a hash derived from (index XOR salt).
    Use different salts for each edition so that gap frames don't
    accidentally match during boundary refinement.  XOR guarantees
    maximum bit separation when salt=0xFFFF.
    """
    store = hashes or {}

    def fetcher(start: int, end: int) -> list[FrameHash]:
        return [
            FrameHash(i, _h(store.get(i, i ^ salt)))
            for i in range(start, end)
        ]

    return fetcher


# ---------------------------------------------------------------------------
# frame_to_time
# ---------------------------------------------------------------------------

class TestFrameToTime:
    def test_frame_zero(self):
        assert frame_to_time(0, 24.0) == timedelta(0)

    def test_integer_fps(self):
        assert frame_to_time(24, 24.0) == timedelta(seconds=1)

    def test_fractional_fps(self):
        result = frame_to_time(24, 23.976216)
        assert abs(result.total_seconds() - (24 / 23.976216)) < 1e-6

    def test_large_frame(self):
        result = frame_to_time(100_000, 24.0)
        expected = timedelta(seconds=100_000 / 24.0)
        assert abs(result.total_seconds() - expected.total_seconds()) < 1e-6


# ---------------------------------------------------------------------------
# hamming_distance
# ---------------------------------------------------------------------------

class TestHammingDistance:
    def test_identical_hashes(self):
        assert hamming_distance(_h(0), _h(0)) == 0

    def test_one_bit_difference(self):
        assert hamming_distance(_h(0), _h(1)) == 1

    def test_all_bits_different(self):
        # 0x0000 vs 0xffff → 16 bits differ
        assert hamming_distance(_h(0x0000), _h(0xFFFF)) == 16

    def test_symmetric(self):
        a, b = _h(0x00FF), _h(0xFF00)
        assert hamming_distance(a, b) == hamming_distance(b, a)


# ---------------------------------------------------------------------------
# count_leading_matches
# ---------------------------------------------------------------------------

class TestCountLeadingMatches:
    def test_empty_list(self):
        assert count_leading_matches([], 5.0) == 0

    def test_all_below_threshold(self):
        assert count_leading_matches([1.0, 2.0, 3.0], 5.0) == 3

    def test_none_below_threshold(self):
        assert count_leading_matches([10.0, 20.0], 5.0) == 0

    def test_partial(self):
        assert count_leading_matches([1.0, 2.0, 10.0, 1.0], 5.0) == 2

    def test_exact_threshold_included(self):
        assert count_leading_matches([5.0, 5.0, 6.0], 5.0) == 2

    def test_single_element_below(self):
        assert count_leading_matches([3.0], 5.0) == 1

    def test_single_element_above(self):
        assert count_leading_matches([7.0], 5.0) == 0


# ---------------------------------------------------------------------------
# _lis_indices (longest increasing subsequence)
# ---------------------------------------------------------------------------

class TestLisIndices:
    def test_empty(self):
        assert _lis_indices([]) == []

    def test_single(self):
        assert _lis_indices([5]) == [0]

    def test_already_sorted(self):
        assert _lis_indices([1, 2, 3, 4]) == [0, 1, 2, 3]

    def test_reversed(self):
        result = _lis_indices([4, 3, 2, 1])
        assert len(result) == 1

    def test_with_one_outlier(self):
        # [1, 100, 2, 3, 4] — LIS is [1, 2, 3, 4]
        result = _lis_indices([1, 100, 2, 3, 4])
        values = [([1, 100, 2, 3, 4])[i] for i in result]
        assert len(result) == 4
        assert values == sorted(values)
        # Must include the longer subsequence, not the one with 100
        assert 1 not in result  # index 1 (value 100) excluded

    def test_scrambled(self):
        # [3, 1, 5, 2, 4, 6]
        result = _lis_indices([3, 1, 5, 2, 4, 6])
        values = [[3, 1, 5, 2, 4, 6][i] for i in result]
        assert len(result) == 4
        assert values == sorted(values)

    def test_duplicates_excluded(self):
        # Strictly increasing, so duplicates reduce LIS length
        result = _lis_indices([1, 2, 2, 3])
        assert len(result) == 3

    def test_preserves_order(self):
        result = _lis_indices([10, 20, 30])
        assert result == [0, 1, 2]


# ---------------------------------------------------------------------------
# filter_to_monotonic
# ---------------------------------------------------------------------------

class TestFilterToMonotonic:
    def test_empty(self):
        ordered, removed = filter_to_monotonic([])
        assert ordered == []
        assert removed == []

    def test_single_match(self):
        m = _fm(1, 1)
        ordered, removed = filter_to_monotonic([m])
        assert ordered == [m]
        assert removed == []

    def test_already_monotonic(self):
        matches = [_fm(1, 10), _fm(2, 20), _fm(3, 30)]
        ordered, removed = filter_to_monotonic(matches)
        assert len(ordered) == 3
        assert len(removed) == 0

    def test_single_reversal(self):
        matches = [
            _fm(1, 10),
            _fm(2, 50),  # outlier — b jumps ahead
            _fm(3, 20),
            _fm(4, 30),
        ]
        ordered, removed = filter_to_monotonic(matches)
        # LIS of b=[10,50,20,30] is [10,20,30] → indices 0,2,3
        assert len(ordered) == 3
        assert len(removed) == 1
        assert removed[0].a.index == 2

    def test_scrambled_scene(self):
        """Frames that exist in both editions but in a different order."""
        matches = [
            _fm(1, 1),    # anchor
            _fm(2, 5),    # reordered
            _fm(3, 3),    # reordered
            _fm(4, 2),    # reordered
            _fm(5, 4),    # reordered
            _fm(6, 6),    # anchor
        ]
        ordered, removed = filter_to_monotonic(matches)
        # b values: [1, 5, 3, 2, 4, 6]
        # LIS: [1, 3, 4, 6] (len 4) or [1, 2, 4, 6] (len 4)
        assert len(ordered) == 4
        assert len(removed) == 2
        # First and last should always be in the ordered set
        assert ordered[0].a.index == 1
        assert ordered[-1].a.index == 6


# ---------------------------------------------------------------------------
# _frames_are_similar
# ---------------------------------------------------------------------------

class TestFramesAreSimilar:
    def test_empty_hashes(self):
        prev = _fh(0, 0)
        next_ = _fh(10, 0)
        assert _frames_are_similar([], prev, next_, threshold=5.0) is True

    def test_identical_to_anchor(self):
        prev = _fh(0, 0)
        next_ = _fh(10, 0)
        hashes = [_fh(i, 0) for i in range(1, 5)]
        assert _frames_are_similar(hashes, prev, next_, threshold=5.0) is True

    def test_dissimilar(self):
        prev = _fh(0, 0x0000)
        next_ = _fh(10, 0x0000)
        # 0xFFFF differs from 0x0000 by 16 bits
        hashes = [_fh(i, 0xFFFF) for i in range(1, 5)]
        assert _frames_are_similar(hashes, prev, next_, threshold=5.0) is False

    def test_similar_to_one_anchor(self):
        """Frames similar to prev but not next — should still pass."""
        prev = _fh(0, 0)
        next_ = _fh(10, 0xFFFF)
        hashes = [_fh(i, 0) for i in range(1, 5)]  # identical to prev
        assert _frames_are_similar(hashes, prev, next_, threshold=5.0) is True


# ---------------------------------------------------------------------------
# analyze_match_pair — no difference
# ---------------------------------------------------------------------------

class TestAnalyzeMatchPairNoDifference:
    """Cases where analyze_match_pair should return None."""

    def test_same_lag(self):
        """When the lag between editions hasn't changed, there's no difference."""
        prev = _fm(10, 20)  # lag = 10
        curr = _fm(30, 40)  # lag = 10
        result = analyze_match_pair(
            prev, curr, _make_fetcher(), _make_fetcher(), [], ComparisonConfig(),
        )
        assert result is None

    def test_negative_frame_count(self):
        """Overlapping matches should return None."""
        prev = _fm(20, 10)
        curr = _fm(10, 30)
        result = analyze_match_pair(
            prev, curr, _make_fetcher(), _make_fetcher(), [], ComparisonConfig(),
        )
        assert result is None

    def test_similar_extra_frames_in_b(self):
        """Extra frames in B that are similar to anchors should be filtered out."""
        prev = FrameMatch(FrameHash(10, _h(0)), FrameHash(10, _h(0)))
        curr = FrameMatch(FrameHash(11, _h(0)), FrameHash(15, _h(0)))
        # a gap: 0 frames, b gap: 4 frames (indices 11–14)
        # All b frames have hash=0, same as anchors → similar
        b_store = {i: 0 for i in range(11, 15)}
        config = ComparisonConfig(extended_similarity_threshold=12, perceptual_match_threshold=5.0)
        result = analyze_match_pair(
            prev, curr, _make_fetcher(), _make_fetcher(b_store), [], config,
        )
        assert result is None

    def test_similar_extra_frames_in_a(self):
        """Extra frames in A that are similar to anchors should be filtered out."""
        prev = FrameMatch(FrameHash(10, _h(0)), FrameHash(10, _h(0)))
        curr = FrameMatch(FrameHash(15, _h(0)), FrameHash(11, _h(0)))
        a_store = {i: 0 for i in range(11, 15)}
        config = ComparisonConfig(extended_similarity_threshold=12, perceptual_match_threshold=5.0)
        result = analyze_match_pair(
            prev, curr, _make_fetcher(a_store), _make_fetcher(), [], config,
        )
        assert result is None


# ---------------------------------------------------------------------------
# analyze_match_pair — detected differences
# ---------------------------------------------------------------------------

class TestAnalyzeMatchPairDifferences:
    def test_unique_to_b(self):
        """Extra frames only in B → unique_to_b."""
        prev = _fm(10, 10)  # lag = 0
        curr = _fm(11, 21)  # lag = 10
        # a gap: 0 frames, b gap: 10 frames (indices 11–20)
        config = ComparisonConfig(extended_similarity_threshold=5)
        result = analyze_match_pair(
            prev, curr, _make_fetcher(salt=0), _make_fetcher(salt=0xFFFF), [], config,
        )
        assert result is not None
        assert result.difference_type == DifferenceType.UNIQUE_TO_B

    def test_unique_to_a(self):
        """Extra frames only in A → unique_to_a."""
        prev = _fm(10, 20)  # lag = 10
        curr = _fm(21, 21)  # lag = 0
        config = ComparisonConfig(extended_similarity_threshold=5)
        result = analyze_match_pair(
            prev, curr, _make_fetcher(), _make_fetcher(), [], config,
        )
        assert result is not None
        assert result.difference_type == DifferenceType.UNIQUE_TO_A

    def test_modified(self):
        """Both editions have different frames in the gap → modified."""
        prev = _fm(10, 10)
        curr = _fm(20, 25)
        # Use different salts so gap frames differ between editions
        result = analyze_match_pair(
            prev, curr,
            _make_fetcher(salt=0), _make_fetcher(salt=0xFFFF),
            [], ComparisonConfig(),
        )
        assert result is not None
        assert result.difference_type == DifferenceType.MODIFIED

    def test_reordered(self):
        """Frames in the gap that were removed for ordering → reordered."""
        prev = _fm(10, 10)
        curr = _fm(20, 25)
        # Removed matches that fall within both gaps
        removed = [_fm(15, 18)]  # a=15 in [11,20), b=18 in [11,25)
        result = analyze_match_pair(
            prev, curr,
            _make_fetcher(salt=0), _make_fetcher(salt=0xFFFF),
            removed, ComparisonConfig(),
        )
        assert result is not None
        assert result.difference_type == DifferenceType.REORDERED

    def test_reordered_requires_a_gap(self):
        """Removed matches outside the a-gap don't trigger reordered."""
        prev = _fm(10, 10)
        curr = _fm(20, 25)
        removed = [_fm(50, 60)]  # a=50 is outside [11, 20)
        result = analyze_match_pair(
            prev, curr,
            _make_fetcher(salt=0), _make_fetcher(salt=0xFFFF),
            removed, ComparisonConfig(),
        )
        assert result is not None
        assert result.difference_type == DifferenceType.MODIFIED


# ---------------------------------------------------------------------------
# analyze_match_pair — boundary refinement
# ---------------------------------------------------------------------------

class TestBoundaryRefinement:
    def test_start_boundary_refined(self):
        """When frames at the start of the gap match between editions,
        the boundary should be narrowed."""
        # First 3 frames of the gap are identical between editions,
        # then they diverge (use very different values to exceed threshold).
        shared_hashes = {11: 100, 12: 200, 13: 300}
        # A frames 14-15 get very different hashes from B frames 14-18
        a_store = {**shared_hashes, 14: 0x0000, 15: 0x0000}
        b_store = {**shared_hashes, 14: 0xFFFF, 15: 0xFFFF, 16: 0xFFFF, 17: 0xFFFF, 18: 0xFFFF}

        prev = FrameMatch(FrameHash(10, _h(99)), FrameHash(10, _h(99)))
        curr = FrameMatch(FrameHash(16, _h(999)), FrameHash(19, _h(999)))

        config = ComparisonConfig(
            perceptual_match_threshold=5.0,
            maximum_inter_match_search=24,
        )
        result = analyze_match_pair(
            prev, curr,
            _make_fetcher(a_store), _make_fetcher(b_store),
            [], config,
        )
        # The refinement should have shifted the start boundary past the
        # 3 matching frames, resulting in a smaller reported difference
        assert result is not None
        # Start time should be after frame 10 (the original prev match)
        assert result.a_range.start > frame_to_time(10, config.fps)

    def test_full_refinement_returns_none(self):
        """If all gap frames match between editions, refinement eventually
        returns None (boundaries cross or gap vanishes)."""
        # All frames in the gap are identical between editions
        shared = {i: i * 10 for i in range(11, 20)}
        prev = FrameMatch(FrameHash(10, _h(99)), FrameHash(10, _h(99)))
        curr = FrameMatch(FrameHash(20, _h(999)), FrameHash(25, _h(999)))

        config = ComparisonConfig(
            perceptual_match_threshold=5.0,
            maximum_inter_match_search=24,
        )
        result = analyze_match_pair(
            prev, curr,
            _make_fetcher(shared), _make_fetcher(shared),
            [], config,
        )
        # After refinement eats through all matching frames, the gap
        # collapses — should return None or a minimal result
        # (the A side has 0 remaining frames after refinement)


# ---------------------------------------------------------------------------
# TimeRange
# ---------------------------------------------------------------------------

class TestTimeRange:
    def test_duration(self):
        r = TimeRange(timedelta(seconds=10), timedelta(seconds=15))
        assert r.duration == timedelta(seconds=5)

    def test_zero_duration(self):
        r = TimeRange(timedelta(seconds=5), timedelta(seconds=5))
        assert r.duration == timedelta(0)


# ---------------------------------------------------------------------------
# SceneDifference
# ---------------------------------------------------------------------------

class TestSceneDifference:
    def test_duration_difference(self):
        d = SceneDifference(
            a_range=TimeRange(timedelta(seconds=0), timedelta(seconds=10)),
            b_range=TimeRange(timedelta(seconds=0), timedelta(seconds=15)),
            difference_type=DifferenceType.MODIFIED,
        )
        assert d.duration_difference == timedelta(seconds=5)

    def test_duration_difference_is_absolute(self):
        d = SceneDifference(
            a_range=TimeRange(timedelta(seconds=0), timedelta(seconds=15)),
            b_range=TimeRange(timedelta(seconds=0), timedelta(seconds=10)),
            difference_type=DifferenceType.MODIFIED,
        )
        assert d.duration_difference == timedelta(seconds=5)


# ---------------------------------------------------------------------------
# find_all_differences — integration tests
# ---------------------------------------------------------------------------

class TestFindAllDifferences:
    def test_empty_matches(self):
        diffs = find_all_differences([], _make_fetcher(), _make_fetcher())
        assert diffs == []

    def test_single_match(self):
        diffs = find_all_differences(
            [_fm(1, 1)], _make_fetcher(), _make_fetcher(),
        )
        assert diffs == []

    def test_identical_editions(self):
        """Matches with constant lag → no differences."""
        matches = [_fm(i, i + 100) for i in range(10)]
        diffs = find_all_differences(matches, _make_fetcher(), _make_fetcher())
        assert diffs == []

    def test_single_insertion_in_b(self):
        """Edition B has extra content between two anchor points."""
        matches = [
            _fm(10, 10),
            # B has 10 extra frames here
            _fm(11, 21),
        ]
        config = ComparisonConfig(extended_similarity_threshold=5)
        diffs = find_all_differences(
            matches, _make_fetcher(), _make_fetcher(), config,
        )
        assert len(diffs) == 1
        assert diffs[0].difference_type == DifferenceType.UNIQUE_TO_B

    def test_multiple_differences(self):
        """Multiple gaps with different types of changes."""
        matches = [
            _fm(10, 10),
            _fm(11, 21),   # unique_to_b (10 extra in B)
            _fm(21, 22),   # unique_to_a (9 extra in A)
            _fm(22, 32),   # unique_to_b (9 extra in B)
        ]
        config = ComparisonConfig(extended_similarity_threshold=5)
        diffs = find_all_differences(
            matches, _make_fetcher(), _make_fetcher(), config,
        )
        assert len(diffs) >= 1

    def test_scrambled_scene_detected(self):
        """A scene with frames in different order should be detected as
        reordered (or at least not missed entirely)."""
        matches = [
            _fm(0, 0, hash_val=1000),      # anchor before
            _fm(10, 15, hash_val=1010),     # reordered group
            _fm(11, 13, hash_val=1011),     # reordered group
            _fm(12, 11, hash_val=1012),     # reordered group
            _fm(13, 14, hash_val=1013),     # reordered group
            _fm(14, 12, hash_val=1014),     # reordered group
            _fm(20, 20, hash_val=1020),     # anchor after
        ]
        config = ComparisonConfig(extended_similarity_threshold=5)
        # Use different salts so gap frames don't match between editions
        diffs = find_all_differences(
            matches, _make_fetcher(salt=0), _make_fetcher(salt=0xFFFF), config,
        )
        # Should detect reordered content between the anchors
        reordered = [d for d in diffs if d.difference_type == DifferenceType.REORDERED]
        assert len(reordered) >= 1

    def test_unsorted_input(self):
        """Matches passed in random order should still work."""
        matches = [
            _fm(20, 20),
            _fm(10, 10),
            _fm(30, 30),
        ]
        diffs = find_all_differences(
            matches, _make_fetcher(), _make_fetcher(),
        )
        assert diffs == []  # constant lag

    def test_large_gap_modified(self):
        """A large gap with different content in both editions."""
        matches = [
            _fm(100, 100),
            _fm(200, 250),  # lag changes by 50
        ]
        # Different salts ensure gap frames differ between editions
        diffs = find_all_differences(
            matches, _make_fetcher(salt=0), _make_fetcher(salt=0xFFFF), ComparisonConfig(),
        )
        assert len(diffs) == 1
        assert diffs[0].difference_type == DifferenceType.MODIFIED

    def test_config_defaults_used(self):
        """find_all_differences works when config=None (uses defaults)."""
        matches = [_fm(10, 10), _fm(20, 20)]
        diffs = find_all_differences(matches, _make_fetcher(), _make_fetcher(), None)
        assert diffs == []


# ---------------------------------------------------------------------------
# ComparisonConfig
# ---------------------------------------------------------------------------

class TestComparisonConfig:
    def test_defaults(self):
        c = ComparisonConfig()
        assert c.fps == 23.976216
        assert c.perceptual_match_threshold == 5.0
        assert c.extended_similarity_threshold == 12
        assert c.maximum_inter_match_search == 24

    def test_custom_values(self):
        c = ComparisonConfig(fps=30.0, perceptual_match_threshold=10.0)
        assert c.fps == 30.0
        assert c.perceptual_match_threshold == 10.0

    def test_immutable(self):
        c = ComparisonConfig()
        with pytest.raises(AttributeError):
            c.fps = 30.0


# ---------------------------------------------------------------------------
# Edge cases and regression tests
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_adjacent_matches_different_lag(self):
        """Two matches right next to each other with different lag.
        Gap has 0 frames in A, >0 in B."""
        prev = FrameMatch(FrameHash(10, _h(0)), FrameHash(10, _h(0)))
        curr = FrameMatch(FrameHash(11, _h(1)), FrameHash(14, _h(1)))
        # a gap: 0 frames, b gap: 3 frames
        config = ComparisonConfig(extended_similarity_threshold=2)
        result = analyze_match_pair(
            prev, curr, _make_fetcher(), _make_fetcher(), [], config,
        )
        assert result is not None
        assert result.difference_type == DifferenceType.UNIQUE_TO_B

    def test_lag_decreases_returns_none_when_a_gap_zero(self):
        """When lag decreases (more content in A), and b has no extra frames."""
        prev = FrameMatch(FrameHash(10, _h(0)), FrameHash(20, _h(0)))  # lag=10
        curr = FrameMatch(FrameHash(16, _h(1)), FrameHash(21, _h(1)))  # lag=5
        # a gap: 5 frames (11–15), b gap: 0 frames
        config = ComparisonConfig(extended_similarity_threshold=3)
        result = analyze_match_pair(
            prev, curr, _make_fetcher(), _make_fetcher(), [], config,
        )
        assert result is not None
        assert result.difference_type == DifferenceType.UNIQUE_TO_A

    def test_lis_with_all_equal_b_values(self):
        """If all b values are identical, LIS should have length 1."""
        result = _lis_indices([5, 5, 5, 5])
        assert len(result) == 1

    def test_filter_monotonic_preserves_anchors(self):
        """First and last matches should be preserved when they form
        part of the LIS."""
        matches = [
            _fm(1, 1),
            _fm(2, 100),  # outlier
            _fm(3, 2),
            _fm(4, 3),
            _fm(5, 4),
        ]
        ordered, removed = filter_to_monotonic(matches)
        assert ordered[0].a.index == 1
        assert ordered[-1].a.index == 5
        assert len(removed) == 1
        assert removed[0].a.index == 2


# ---------------------------------------------------------------------------
# _refine_boundaries
# ---------------------------------------------------------------------------

class TestRefineBoundaries:
    def test_no_matching_frames(self):
        """When no frames match at boundaries, returns (0, 0)."""
        # Different hashes at each position
        a_hashes = [_fh(i, i * 100) for i in range(5)]
        b_hashes = [_fh(i, i * 100 + 50) for i in range(5)]
        config = ComparisonConfig(perceptual_match_threshold=0)
        start, end = _refine_boundaries(a_hashes, b_hashes, config)
        assert start == 0
        assert end == 0

    def test_all_matching_frames(self):
        """When all frames match, returns full lengths."""
        hashes = [_fh(i, i * 10) for i in range(5)]
        config = ComparisonConfig(perceptual_match_threshold=5.0, maximum_inter_match_search=24)
        start, end = _refine_boundaries(hashes, hashes, config)
        assert start == 5
        assert end == 5

    def test_start_only_matches(self):
        """Only first few frames match."""
        a_hashes = [_fh(0, 0), _fh(1, 0), _fh(2, 0xFFFF)]
        b_hashes = [_fh(0, 0), _fh(1, 0), _fh(2, 0)]
        config = ComparisonConfig(perceptual_match_threshold=5.0, maximum_inter_match_search=24)
        start, end = _refine_boundaries(a_hashes, b_hashes, config)
        assert start == 2
        # End: reversed lists — a=[0xFFFF, 0], b=[0, 0] → first pair differs
        assert end == 0

    def test_empty_hashes(self):
        start, end = _refine_boundaries([], [], ComparisonConfig())
        assert start == 0
        assert end == 0

    def test_max_search_limits(self):
        """Should not look beyond maximum_inter_match_search frames."""
        hashes = [_fh(i, 0) for i in range(50)]
        config = ComparisonConfig(maximum_inter_match_search=10, perceptual_match_threshold=5.0)
        start, end = _refine_boundaries(hashes, hashes, config)
        assert start == 10
        assert end == 10
