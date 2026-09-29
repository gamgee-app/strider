"""Comparing a film takes work in proportion to the film, not to its square.

A film is a third of a million frames a side. On a real one the comparison
did not finish, then took half a minute, and neither the scenarios nor the
film itself said which was to be expected of the next change. These say.
"""

import time

import pytest

from movie_edition_comparer import compare_hashes
from tests.performance.synthetic import synthetic_film


def compare_counting(frames: int, monkeypatch) -> tuple[int, int, float]:
    """Compare a made-up film of this many frames: how many runs it had,
    how many pairs of runs were looked at, and how long it took.

    A pair of runs looked at is one call of same_picture, which is what the
    comparison spends its time on once the hashes are in memory.
    """
    a, b = synthetic_film(frames)
    a_runs = compare_hashes.runs_of([compare_hashes.Frame(i, *f) for i, f in enumerate(a)])
    b_runs = compare_hashes.runs_of([compare_hashes.Frame(i, *f) for i, f in enumerate(b)])

    looked_at = 0
    same_picture = compare_hashes.same_picture

    def counting(x, y):
        nonlocal looked_at
        looked_at += 1
        return same_picture(x, y)

    monkeypatch.setattr(compare_hashes, "same_picture", counting)
    started = time.perf_counter()
    compare_hashes.compare_runs(a_runs, b_runs)
    return len(a_runs) + len(b_runs), looked_at, time.perf_counter() - started


def test_the_work_grows_with_the_film_and_not_with_its_square(monkeypatch):
    """Four times the film should mean about four times the pairs looked at.

    Sixteen times would mean every free run is being held up against every
    other, which is what a letterboxed film does to an index that does not
    know its bars are on every frame.
    """
    small_runs, small_looked, _ = compare_counting(5_000, monkeypatch)
    large_runs, large_looked, _ = compare_counting(20_000, monkeypatch)
    grew = large_looked / small_looked
    assert grew < 2 * (large_runs / small_runs), (
        f"{large_runs / small_runs:.1f}x the runs took {grew:.1f}x the pairs looked at")


def test_a_run_is_held_against_few_others(monkeypatch):
    """Whatever the film, a run is compared with a handful of others, not
    with a share of the film."""
    runs, looked_at, _ = compare_counting(20_000, monkeypatch)
    assert looked_at / runs < 5, f"{looked_at / runs:.1f} pairs looked at per run"


def test_twenty_thousand_frames_compare_in_seconds(monkeypatch):
    """Coarse, for a machine's sake: a sixteenth of a film in well under
    the time a whole one should take."""
    _, _, seconds = compare_counting(20_000, monkeypatch)
    assert seconds < 10, f"took {seconds:.1f}s"
