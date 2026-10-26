"""Checking links by block averages puts the frames of a still shot back in
order, as two masters of a film leave them: every frame of the shot about as
near as the next, so that the nearest is as often a neighbour as the frame
itself."""

import numpy as np

from movie_edition_comparer.compare_hashes import Alignment, Run, check_by_averages


def editions(looks: str, early: int = 0, seed: int = 0):
    """Two masters of one footage, as runs and block averages. Each letter of
    looks is a frame: m one that moves, its picture its own; s one of a still
    shot, its picture all but its neighbours'; k one of black; g one edition b grades further
    from edition a's than the same-picture limit, though not so far as to be
    another picture; r one edition b replaces with another picture. Edition
    b starts early frames early, with pictures of its own."""
    rng = np.random.default_rng(seed)
    still = rng.uniform(30, 220, 256)
    pictures = [still + rng.normal(0, 0.05, 256) if kind == "s" else np.full(256, 16.0) if kind == "k"
                else rng.uniform(30, 220, 256) for kind in looks]
    a = np.array(pictures, np.float32) + rng.normal(0, 0.1, (len(looks), 256)).astype(np.float32)
    b = np.array(pictures) + rng.normal(0, 0.1, (len(looks), 256))
    for k, kind in enumerate(looks):
        if kind == "k":
            a[k] = b[k] = 16
        elif kind == "g":
            b[k] += rng.normal(0, 1.3, 256)
        elif kind == "r":
            b[k] = rng.uniform(30, 220, 256)
    b = np.concatenate([rng.uniform(30, 220, (early, 256)), b]).astype(np.float32)
    a_runs = [Run(i, 1, f"a{i}", "0" * 64) for i in range(len(a))]
    b_runs = [Run(j, 1, f"b{j}", "0" * 64) for j in range(len(b))]
    return Alignment(a_runs, b_runs), a, b


def test_a_still_shot_linked_out_of_order_between_moving_frames_is_put_in_order():
    looks = "mmm" + "s" * 10 + "mmm"
    alignment, a, b = editions(looks)
    crossed = {4: 6, 6: 4, 8: 9, 9: 8}
    for i in range(len(looks)):
        alignment.link(i, crossed.get(i, i))
    check_by_averages(alignment, a, b, fill=True)
    assert alignment.pairs() == [(i, i) for i in range(len(looks))]


def test_a_still_shot_linked_a_frame_off_takes_the_offset_of_the_footage_around_it():
    looks = "m" * 40 + "s" * 12
    alignment, a, b = editions(looks, early=3)
    for i in range(40):
        alignment.link(i, i + 3)
    for i in range(40, 51):
        alignment.link(i, i + 4)
    check_by_averages(alignment, a, b, fill=True)
    assert alignment.pairs() == [(i, i + 3) for i in range(len(looks))]


def test_a_shot_graded_apart_is_linked_where_the_footage_around_it_puts_it():
    looks = "mmm" + "g" * 5 + "mmm"
    alignment, a, b = editions(looks)
    for i in (0, 1, 2, 8, 9, 10):
        alignment.link(i, i)
    check_by_averages(alignment, a, b, fill=True)
    assert alignment.pairs() == [(i, i) for i in range(len(looks))]


def test_a_shot_replaced_by_another_is_left_unlinked_however_the_footage_around_it_is_placed():
    looks = "mmm" + "r" * 5 + "mmm"
    alignment, a, b = editions(looks)
    for i in (0, 1, 2, 8, 9, 10):
        alignment.link(i, i)
    check_by_averages(alignment, a, b, fill=True)
    assert alignment.pairs() == [(i, i) for i in (0, 1, 2, 8, 9, 10)]


def flats(a, b):
    return a.std(axis=1) < 2, b.std(axis=1) < 2


def test_black_between_footage_both_editions_hold_is_linked():
    looks = "mmm" + "kkk" + "mmm"
    alignment, a, b = editions(looks)
    for i in range(len(looks)):
        alignment.link(i, i)
    check_by_averages(alignment, a, b, 1.0, *flats(a, b), fill=True)
    assert alignment.pairs() == [(i, i) for i in range(len(looks))]


def test_black_between_footage_that_differs_is_not_linked():
    from movie_edition_comparer.compare_hashes import FLAT_HELD
    looks = "mmm" + "r" * FLAT_HELD + "kkk" + "r" * FLAT_HELD + "mmm"
    alignment, a, b = editions(looks)
    for i in range(len(looks)):
        alignment.link(i, i)
    check_by_averages(alignment, a, b, 1.0, *flats(a, b), fill=True)
    assert alignment.pairs() == [(i, i) for i, kind in enumerate(looks) if kind == "m"]


def test_black_held_as_one_frame_is_split_to_line_up_with_black_held_as_many():
    from movie_edition_comparer.compare_hashes import _split_flat
    runs = [Run(0, 2, "m", "0" * 64), Run(2, 3, "k", "0" * 64), Run(5, 1, "n", "0" * 64)]
    flat = np.array([False, False, True, True, True, False])
    assert [(run.start, run.count) for run in _split_flat(runs, flat)] == [(0, 2), (2, 1), (3, 1), (4, 1), (5, 1)]
