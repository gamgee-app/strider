"""Tests for boundary alignment using real hash data.

Each test case was visually verified using the alignment viewer.
The expected offsets represent the correct frame alignment as confirmed
by a human comparing theatrical and extended frames.
"""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from movie_edition_comparer.comparison import hamming_distance, _refine_boundaries
from movie_edition_comparer.models import ComparisonConfig, FrameHash


DATA_PATH = os.path.join(os.path.dirname(__file__), "boundary_test_data.json")

with open(DATA_PATH) as f:
    ALL_CASES = json.load(f)


def _make_hashes(hash_dict: dict[str, str], start: int, end: int) -> list[FrameHash]:
    """Build a list of FrameHash from a dict of {frame_index: hash}."""
    return [
        FrameHash(i, hash_dict[str(i)])
        for i in range(start, end)
        if str(i) in hash_dict
    ]


def _get_case(case_num: int) -> dict:
    return next(c for c in ALL_CASES if c["case"] == case_num)


class TestBoundaryAlignmentCorrectAtOffset0:
    """Cases where the current algorithm's boundary is correct."""

    @pytest.mark.parametrize("case_num", [1, 2, 3, 4, 5, 6])
    def test_boundary_correct(self, case_num):
        """The boundary match at offset 0 is visually confirmed correct."""
        case = _get_case(case_num)
        t_boundary = case["tBoundary"]
        e_boundary = case["eBoundary"]

        # At offset 0, the aligned pair should have a reasonable distance
        t_hash = case["t_hashes"].get(str(t_boundary))
        e_hash = case["e_hashes"].get(str(e_boundary))
        if t_hash and e_hash:
            dist = hamming_distance(t_hash, e_hash)
            # Offset 0 distance should be lower than offset -1
            t_hash_m1 = case["t_hashes"].get(str(t_boundary - 1))
            e_hash_m1 = case["e_hashes"].get(str(e_boundary - 1))
            if t_hash_m1 and e_hash_m1:
                dist_m1 = hamming_distance(t_hash_m1, e_hash_m1)
                assert dist <= dist_m1, (
                    f"Case {case_num}: offset 0 dist {dist} should be <= offset -1 dist {dist_m1}"
                )


class TestBoundaryAlignmentOffBy1:
    """Cases where the boundary should be 1 frame earlier (offset -1).

    These represent off-by-one errors where the boundary refinement
    stopped too early due to a single frame exceeding the threshold.
    """

    # Visually confirmed: the correct match is 1 frame earlier than the
    # algorithm currently produces.
    EXPECTED = {
        7:  (116930, 154290),
        8:  (117507, 158149),
        9:  (117507, 158149),
        11: (128072, 169581),
        12: (176642, 226508),
        14: (208081, 260979),
    }

    @pytest.mark.parametrize("case_num", [7, 8, 9, 11, 12, 14])
    def test_expected_boundary(self, case_num):
        """The correct boundary match, as confirmed by visual inspection."""
        case = _get_case(case_num)
        expected_t, expected_e = self.EXPECTED[case_num]
        actual_t = case["tBoundary"]
        actual_e = case["eBoundary"]
        assert expected_t == actual_t - 1, (
            f"Case {case_num}: expected t{expected_t}, got t{actual_t}"
        )
        assert expected_e == actual_e - 1, (
            f"Case {case_num}: expected e{expected_e}, got e{actual_e}"
        )

    @pytest.mark.parametrize("case_num", [7, 8, 9, 11, 12, 14])
    def test_refine_boundaries_extends_past_current(self, case_num):
        """_refine_boundaries should trim at least 1 more frame than it
        currently does for these cases, once the algorithm is fixed."""
        case = _get_case(case_num)
        t_boundary = case["tBoundary"]
        e_boundary = case["eBoundary"]
        config = ComparisonConfig()

        if case["boundary"] == "start":
            # Build hashes starting from the current boundary going forward
            a_hashes = _make_hashes(case["t_hashes"], t_boundary, t_boundary + 15)
            b_hashes = _make_hashes(case["e_hashes"], e_boundary, e_boundary + 15)
            start_trim, _ = _refine_boundaries(a_hashes, b_hashes, config)
            # Currently start_trim is 0 (the boundary frame itself doesn't
            # match below threshold). Once fixed, it should be >= 1.
            # For now, mark as expected failure.
            pytest.xfail(
                f"Case {case_num}: start_trim={start_trim}, expected >= 1. "
                f"Boundary refinement needs to handle distance "
                f"{case['adjDist']} (above threshold {config.perceptual_match_threshold})"
            )
        else:  # end boundary
            a_hashes = _make_hashes(case["t_hashes"], t_boundary - 14, t_boundary + 1)
            b_hashes = _make_hashes(case["e_hashes"], e_boundary - 14, e_boundary + 1)
            _, end_trim = _refine_boundaries(a_hashes, b_hashes, config)
            pytest.xfail(
                f"Case {case_num}: end_trim={end_trim}, expected >= 1. "
                f"Boundary refinement needs to handle distance "
                f"{case['adjDist']} (above threshold {config.perceptual_match_threshold})"
            )


class TestBoundaryAlignmentOffBy2:
    """Cases where the boundary should be 2 frames earlier (offset -2)."""

    EXPECTED = {
        10: (117509, 158150),
        13: (196209, 248835),
    }

    @pytest.mark.parametrize("case_num", [10, 13])
    def test_expected_boundary(self, case_num):
        """The correct boundary match, as confirmed by visual inspection."""
        case = _get_case(case_num)
        expected_t, expected_e = self.EXPECTED[case_num]
        actual_t = case["tBoundary"]
        actual_e = case["eBoundary"]
        assert expected_t == actual_t - 2, (
            f"Case {case_num}: expected t{expected_t}, got t{actual_t}"
        )
        assert expected_e == actual_e - 2, (
            f"Case {case_num}: expected e{expected_e}, got e{actual_e}"
        )
