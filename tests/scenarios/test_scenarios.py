"""The specification: what comparing two editions of a film should report.

Every scenario in tests/catalogue.py describes two editions and works out, by
comparing them, what the differences between them are. These tests assert that.

They are not a record of what the comparer currently does. Where it does not
meet the specification, they fail -- that is the point of them.
"""

import pytest

from tests.scenarios.catalogue import CATALOGUE
from tests.scenarios.comparer import compare
from tests.scenarios.editions import accounts_for_every_frame, describe, satisfies

CASES = [pytest.param(scenario, id=scenario.name) for scenario in CATALOGUE]


@pytest.mark.parametrize("scenario", CASES)
def test_reports_the_differences_that_are_there(scenario):
    truth = scenario.expected()
    reported = describe(compare(*scenario.frames()))

    assert satisfies(truth, reported), "\n".join([
        "",
        f"Scenario: {scenario.name}",
        f"  {scenario.story}",
        "",
        f"  edition_a: {scenario.edition_a}",
        f"  edition_b: {scenario.edition_b}",
        "",
        "  the differences that are there:",
        *([f"      {d}" for d in truth] or ["      none"]),
        "",
        "  what was reported:",
        *([f"      {d}" for d in reported] or ["      nothing"]),
    ])


@pytest.mark.parametrize("scenario", CASES)
def test_the_expected_answer_accounts_for_every_frame(scenario):
    """A second opinion on what the harness worked out.

    The differences a scenario expects are derived. This checks them back
    against what the two strings plainly say, so a mistake in that derivation
    shows up here rather than quietly redefining what correct means.
    """
    complaints = accounts_for_every_frame(scenario, scenario.expected())
    assert not complaints, "\n".join([
        "",
        f"Scenario: {scenario.name}",
        f"  edition_a: {scenario.edition_a}",
        f"  edition_b: {scenario.edition_b}",
        "",
        "  the harness expects:",
        *([f"      {d}" for d in scenario.expected()] or ["      nothing"]),
        "",
        "  but the editions say:",
        *[f"      {c}" for c in complaints],
    ])


def test_scenario_names_are_unique():
    names = [s.name for s in CATALOGUE]
    assert len(names) == len(set(names)), "two scenarios share a name"


def test_every_scenario_states_a_truth_it_can_work_out():
    """Every scenario must yield a truth, whether derived or stated."""
    for scenario in CATALOGUE:
        scenario.expected()
