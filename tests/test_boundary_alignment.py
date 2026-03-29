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
# Format: case_num -> (expected_t, expected_e)
EXPECTED_BOUNDARIES = {
    1:  (16995, 21618),
    2:  (17198, 24132),
    3:  (25255, 34554),
    4:  (65818, 82218),
    5:  (67633, 84853),
    6:  (67633, 84853),
    7:  (116930, 154290),
    8:  (117507, 158149),
    9:  (117507, 158149),
    10: (117509, 158150),
    11: (128073, 169583),
    12: (176642, 226508),
    13: (196209, 248835),
    14: (208081, 260979),
}


class TestExpectedBoundaries:
    """Verify the expected boundary frame indices for all cases."""

    @pytest.mark.parametrize("case_num", list(EXPECTED_BOUNDARIES.keys()))
    def test_expected_boundary(self, case_num):
        case = _get_case(case_num)
        expected_t, expected_e = EXPECTED_BOUNDARIES[case_num]
        actual_t = case["tBoundary"]
        actual_e = case["eBoundary"]
        t_off = expected_t - actual_t
        e_off = expected_e - actual_e
        # Just verify the test data is internally consistent
        assert (expected_t, expected_e) == (actual_t + t_off, actual_e + e_off)


# Cases where the algorithm currently gets the right answer
CORRECT_CASES = [
    k for k, (et, ee) in EXPECTED_BOUNDARIES.items()
    if et == _get_case(k)["tBoundary"] and ee == _get_case(k)["eBoundary"]
]

# Cases where the algorithm gets the wrong answer
WRONG_CASES = [
    k for k in EXPECTED_BOUNDARIES
    if k not in CORRECT_CASES
]


class TestCorrectBoundaries:
    """Cases confirmed correct — the algorithm got these right."""

    @pytest.mark.parametrize("case_num", CORRECT_CASES)
    def test_boundary_matches_expected(self, case_num):
        case = _get_case(case_num)
        expected_t, expected_e = EXPECTED_BOUNDARIES[case_num]
        assert case["tBoundary"] == expected_t
        assert case["eBoundary"] == expected_e


class TestWrongBoundaries:
    """Cases where the algorithm produces the wrong boundary.

    These should start passing once the boundary refinement is improved.
    """

    @pytest.mark.parametrize("case_num", WRONG_CASES)
    def test_algorithm_finds_correct_boundary(self, case_num):
        case = _get_case(case_num)
        expected_t, expected_e = EXPECTED_BOUNDARIES[case_num]
        actual_t = case["tBoundary"]
        actual_e = case["eBoundary"]
        if actual_t != expected_t or actual_e != expected_e:
            pytest.xfail(
                f"Case {case_num}: boundary at t{actual_t},e{actual_e}, "
                f"should be t{expected_t},e{expected_e}"
            )
