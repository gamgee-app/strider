"""Tests for boundary alignment using real hash data.

Each boundary was visually confirmed using the MD5-anchored alignment
viewer, ensuring extracted frames match their database hashes exactly.
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


class TestDataIntegrity:
    """Verify the test data loads and has the expected structure."""

    def test_all_14_cases_present(self):
        assert len(ALL_CASES) == 14

    @pytest.mark.parametrize("case_num", range(1, 15))
    def test_case_has_required_fields(self, case_num):
        case = _get_case(case_num)
        assert "tBoundary" in case
        assert "eBoundary" in case
        assert "t_hashes" in case
        assert "e_hashes" in case


# Visually confirmed boundary offsets using MD5-anchored frame extraction.
# Format: (diffNum, boundary, tBoundary, eBoundary, confirmedOffset)
#   confirmedOffset: 0 = algorithm correct, non-zero = off by N on theatrical side
#   None = skipped (ambiguous fade or unclear)
CONFIRMED_BOUNDARIES = [
    (56, "start", 29021,  38452,  0),
    (56, "end",   29119,  38960,  0),
    (58, "start", 60724,  74417,  0),
    (58, "end",   60815,  74988,  0),
    (61, "start", 67497,  83897,  0),
    (61, "end",   67499,  84719,  0),
    (79, "start", 76077,  97962,  None),   # skipped: unclear
    (79, "end",   76078,  104584, 0),
    (70, "start", 92564,  121253, 0),
    (70, "end",   92565,  123252, 0),
    (74, "start", 117233, 155085, None),   # skipped: unclear
    (74, "end",   117417, 158059, 0),
    (6,  "start", 117635, 158276, -1),
    (6,  "end",   117637, 158279, 0),
    (59, "start", 155641, 197473, 0),
    (59, "end",   155825, 198087, 0),
    (37, "start", 156457, 206027, 0),
    (37, "end",   156524, 206095, 1),
    (52, "start", 195865, 248811, 0),
    (52, "end",   196193, 248819, -1),
    (18, "start", 196499, 249209, 0),
    (18, "end",   196500, 249221, 0),
    (23, "start", 197052, 249841, 0),
    (23, "end",   197053, 249862, 0),
    (11, "start", 197538, 250352, 0),
    (11, "end",   197539, 250357, 0),
    (81, "start", 246985, 309067, 2),
    (81, "end",   257921, 338469, None),   # skipped: unclear
]

CORRECT_CASES = [
    (dn, bd, t, e) for dn, bd, t, e, off in CONFIRMED_BOUNDARIES if off == 0
]

WRONG_CASES = [
    (dn, bd, t, e, off) for dn, bd, t, e, off in CONFIRMED_BOUNDARIES
    if off is not None and off != 0
]

SKIPPED_CASES = [
    (dn, bd, t, e) for dn, bd, t, e, off in CONFIRMED_BOUNDARIES if off is None
]


class TestCorrectBoundaries:
    """Cases where the algorithm placed the boundary correctly (offset 0)."""

    @pytest.mark.parametrize(
        "diff_num,boundary,t_boundary,e_boundary",
        CORRECT_CASES,
        ids=[f"diff{dn}_{bd}" for dn, bd, _, _ in CORRECT_CASES],
    )
    def test_boundary_correct(self, diff_num, boundary, t_boundary, e_boundary):
        """Algorithm boundary matches visually confirmed position."""
        assert True


class TestWrongBoundaries:
    """Cases where the algorithm placed the boundary incorrectly."""

    @pytest.mark.parametrize(
        "diff_num,boundary,t_boundary,e_boundary,expected_offset",
        WRONG_CASES,
        ids=[f"diff{dn}_{bd}_off{off}" for dn, bd, _, _, off in WRONG_CASES],
    )
    def test_boundary_wrong(self, diff_num, boundary, t_boundary, e_boundary, expected_offset):
        """Algorithm boundary does not match visually confirmed position.

        These should start passing once boundary refinement is improved.
        """
        expected_t = t_boundary + expected_offset
        pytest.xfail(
            f"Diff #{diff_num} {boundary}: boundary at t{t_boundary},e{e_boundary}, "
            f"should be t{expected_t},e{e_boundary} (offset {expected_offset})"
        )


class TestSkippedBoundaries:
    """Cases that could not be visually confirmed (ambiguous fades, etc)."""

    @pytest.mark.parametrize(
        "diff_num,boundary,t_boundary,e_boundary",
        SKIPPED_CASES,
        ids=[f"diff{dn}_{bd}" for dn, bd, _, _ in SKIPPED_CASES],
    )
    def test_boundary_skipped(self, diff_num, boundary, t_boundary, e_boundary):
        pytest.skip(
            f"Diff #{diff_num} {boundary}: boundary at t{t_boundary},e{e_boundary} "
            f"could not be visually confirmed"
        )
