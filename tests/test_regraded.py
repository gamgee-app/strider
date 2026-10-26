"""Footage in the same place that looks different is reported as regraded,
not as the same: the link says where it is, the grey levels how it looks."""

import numpy as np

from movie_edition_comparer.compare_hashes import (
    REGRADED, Alignment, Run, _regrades, differences_of)


def linked(n):
    a_runs = [Run(i, 1, f"a{i}", "0" * 64) for i in range(n)]
    b_runs = [Run(i, 1, f"b{i}", "0" * 64) for i in range(n)]
    alignment = Alignment(a_runs, b_runs)
    for i in range(n):
        alignment.link(i, i)
    return alignment


def test_a_shot_recoloured_against_the_rest_of_the_film_is_regraded_and_the_rest_is_not():
    rng = np.random.default_rng(0)
    a = rng.uniform(20, 230, (300, 256)).astype(np.float32)
    b = a * 0.6 + 30                      # one master darker and flatter throughout
    b[140:170] = 255 - a[140:170]         # and one shot recoloured
    regrade = _regrades(linked(300), a, b)
    assert all(regrade[i] <= REGRADED for i in list(range(0, 110)) + list(range(200, 300)))
    assert all(regrade[i] > REGRADED for i in range(145, 165))


def test_regraded_runs_are_reported_as_one_stretch_between_reencodings():
    alignment = linked(6)
    regrade = {0: 1.0, 1: 1.0, 2: 20.0, 3: 30.0, 4: 1.0, 5: 1.0}
    found = [(d.kind, d.a.start, d.a.count, d.regrade) for d in differences_of(alignment, set(), lambda a, b: 0, regrade)]
    assert found == [("reencoded", 0, 2, 1.0), ("regraded", 2, 2, 25.0), ("reencoded", 4, 2, 1.0)]
