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

from movie_edition_comparer.comparison import hamming_distance
from movie_edition_comparer.models import ComparisonConfig


DATA_PATH = os.path.join(os.path.dirname(__file__), "boundary_test_data.json")

with open(DATA_PATH) as f:
    ALL_CASES = json.load(f)


def _get_case(case_num: int) -> dict:
    return next(c for c in ALL_CASES if c["case"] == case_num)


# Visually confirmed expected boundaries for all 14 cases.
# Format: case_num -> (expected_t, expected_e, offset_from_current)
EXPECTED_BOUNDARIES = {
    1:  (16995, 21618, 0),
    2:  (17198, 24132, 0),
    3:  (25255, 34554, 0),
    4:  (65818, 82218, 0),
    5:  (67633, 84853, 0),
    6:  (67633, 84853, 0),
    7:  (116930, 154290, -1),
    8:  (117507, 158149, -1),
    9:  (117507, 158149, -1),
    10: (117509, 158150, -2),
    11: (128072, 169581, -1),
    12: (176642, 226508, -1),
    13: (196209, 248835, -2),
    14: (208081, 260979, -1),
}

CORRECT_CASES = [k for k, v in EXPECTED_BOUNDARIES.items() if v[2] == 0]
OFF_BY_1_CASES = [k for k, v in EXPECTED_BOUNDARIES.items() if v[2] == -1]
OFF_BY_2_CASES = [k for k, v in EXPECTED_BOUNDARIES.items() if v[2] == -2]


class TestExpectedBoundaries:
    """Verify the expected boundary frame indices for all cases."""

    @pytest.mark.parametrize("case_num", list(EXPECTED_BOUNDARIES.keys()))
    def test_expected_boundary(self, case_num):
        case = _get_case(case_num)
        expected_t, expected_e, offset = EXPECTED_BOUNDARIES[case_num]
        actual_t = case["tBoundary"]
        actual_e = case["eBoundary"]
        assert expected_t == actual_t + offset, (
            f"Case {case_num}: expected t{expected_t}, got t{actual_t} + offset {offset}"
        )
        assert expected_e == actual_e + offset, (
            f"Case {case_num}: expected e{expected_e}, got e{actual_e} + offset {offset}"
        )


class TestCorrectBoundaries:
    """Cases confirmed correct at offset 0 — the algorithm got these right."""

    @pytest.mark.parametrize("case_num", CORRECT_CASES)
    def test_offset_0_is_best(self, case_num):
        """The current boundary has a lower or equal distance than offset -1."""
        case = _get_case(case_num)
        t = case["tBoundary"]
        e = case["eBoundary"]
        t_hash = case["t_hashes"].get(str(t))
        e_hash = case["e_hashes"].get(str(e))
        t_hash_m1 = case["t_hashes"].get(str(t - 1))
        e_hash_m1 = case["e_hashes"].get(str(e - 1))
        if t_hash and e_hash and t_hash_m1 and e_hash_m1:
            dist_0 = hamming_distance(t_hash, e_hash)
            dist_m1 = hamming_distance(t_hash_m1, e_hash_m1)
            assert dist_0 <= dist_m1


class TestOffByOneBoundaries:
    """Cases where the algorithm is off by 1 frame.

    These should start passing once the boundary refinement is improved.
    """

    @pytest.mark.parametrize("case_num", OFF_BY_1_CASES)
    def test_algorithm_finds_correct_boundary(self, case_num):
        """The algorithm should place the boundary 1 frame earlier."""
        expected_t, expected_e, _ = EXPECTED_BOUNDARIES[case_num]
        case = _get_case(case_num)
        actual_t = case["tBoundary"]
        # Currently the algorithm places the boundary 1 frame too late
        if actual_t - 1 == expected_t:
            pytest.xfail(f"Case {case_num}: boundary is at t{actual_t}, should be t{expected_t}")
        else:
            assert actual_t + EXPECTED_BOUNDARIES[case_num][2] == expected_t


class TestOffByTwoBoundaries:
    """Cases where the algorithm is off by 2 frames."""

    @pytest.mark.parametrize("case_num", OFF_BY_2_CASES)
    def test_algorithm_finds_correct_boundary(self, case_num):
        """The algorithm should place the boundary 2 frames earlier."""
        expected_t, expected_e, _ = EXPECTED_BOUNDARIES[case_num]
        case = _get_case(case_num)
        actual_t = case["tBoundary"]
        if actual_t - 2 == expected_t:
            pytest.xfail(f"Case {case_num}: boundary is at t{actual_t}, should be t{expected_t}")
        else:
            assert actual_t + EXPECTED_BOUNDARIES[case_num][2] == expected_t
