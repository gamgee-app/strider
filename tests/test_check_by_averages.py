"""Checking links by block averages puts the frames of a still shot back in
order, as two masters of a film leave them: every frame of the shot about as
near as the next, so that the nearest is as often a neighbour as the frame
itself."""

import numpy as np

from movie_edition_comparer.compare_hashes import Alignment, Run, check_by_averages


def editions(looks: str, early: int = 0, seed: int = 0):
    """Two masters of one footage, as runs and block averages. Each letter of
    looks is a frame: m one that moves, its picture its own; s one of a still
    shot, its picture all but its neighbours'. Edition b starts early frames
    early, with pictures of its own."""
    rng = np.random.default_rng(seed)
    still = rng.uniform(30, 220, 256)
    pictures = [rng.uniform(30, 220, 256) if kind == "m" else still + rng.normal(0, 0.05, 256) for kind in looks]
    a = np.array(pictures, np.float32) + rng.normal(0, 0.1, (len(looks), 256)).astype(np.float32)
    b = np.concatenate([rng.uniform(30, 220, (early, 256)),
                        np.array(pictures) + rng.normal(0, 0.1, (len(looks), 256))]).astype(np.float32)
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
