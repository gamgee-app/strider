"""Finding pictures near each other by grid finds exactly what measuring every pair finds."""

import numpy as np
import pytest

from movie_edition_comparer.averages import apart
from movie_edition_comparer.compare_averages import best_two, within


def pictures(n, seed, clusters=40, spread=0.6):
    """Pictures in clusters, as a film's shots are: many a fraction of a grey level apart."""
    rng = np.random.default_rng(seed)
    centres = rng.uniform(20, 230, (clusters, 256))
    return (centres[rng.integers(0, clusters, n)] + rng.normal(0, spread, (n, 256))).astype(np.float32)


def every_pair(a, b, reach):
    d = apart(a[:, None, :], b[None, :, :])
    i, j = np.nonzero(d <= reach)
    return set(zip(i.tolist(), j.tolist()))


@pytest.mark.parametrize("reach", [0.5, 1.25, 3.0])
def test_finds_every_pair_within_reach_and_no_other(reach):
    a, b = pictures(700, 1), pictures(900, 2)
    i, j, far = within(a, b, reach)
    assert set(zip(i.tolist(), j.tolist())) == every_pair(a, b, reach)
    assert np.allclose(far, apart(a[i], b[j]), atol=1e-4)


def test_finds_nothing_among_nothing():
    i, j, far = within(np.zeros((0, 256), np.float32), pictures(10, 3), 1.0)
    assert len(i) == len(j) == len(far) == 0


def test_the_best_two_are_the_nearest_and_the_next():
    owner = np.array([0, 0, 0, 2]); other = np.array([5, 6, 7, 8]); far = np.array([0.4, 0.1, 0.3, 0.9], np.float32)
    best, first, second = best_two(owner, other, far, 3)
    assert best.tolist() == [6, -1, 8]
    assert np.allclose(first, [0.1, np.inf, 0.9]) and np.allclose(second, [0.3, np.inf, np.inf])
