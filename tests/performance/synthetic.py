"""Two editions of a film, made up, with what makes a real one slow to compare.

Not a scenario: nothing here says what should be reported. It is a film of
whatever size the test wants, with the shape of a real one -- shots that
match, shots one edition lacks, shots regraded past looking alike, fades
to black, letterbox bars, credits that differ -- for measuring the work
comparing it takes.
"""

import hashlib
import random

HASH_BITS = 256

# The rows above and below a letterboxed picture hash to nought on every
# frame, so every frame shares the pieces of its hash that hold them.
BARS = ((1 << 32) - 1) | (((1 << 36) - 1) << 220)
PICTURE_BITS = range(32, 220)


def synthetic_film(frames: int, seed: int = 1) -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
    """Two editions of about this many frames, as (hash_md5, hash_block_mean_0) each.

    Shots of 20 to 200 frames, a frame in twenty held for four. A tenth of
    frames are dark: a fade or black between scenes is one of a few
    near-black pictures, each frame of it a bit or two off the others.
    Edition b is a separate transfer, so every frame is re-encoded and a
    third are a bit apart to look at as well. It adds shots the other
    lacks, loses a few, regrades a fifth past looking alike, and its
    credits are its own.
    """
    rng = random.Random(seed)
    darks = [sum(1 << bit for bit in rng.sample(PICTURE_BITS, rng.randint(4, 12))) for _ in range(12)]

    def picture(dark: bool) -> int:
        if dark:
            pic = rng.choice(darks)
            for _ in range(rng.randint(0, 2)):
                pic ^= 1 << rng.choice(PICTURE_BITS)
            return pic
        return rng.getrandbits(HASH_BITS) & ~BARS

    def rendering(pic: int, bits_apart: int, transfer: str) -> tuple[str, str]:
        for _ in range(bits_apart):
            pic ^= 1 << rng.choice(PICTURE_BITS)
        return hashlib.md5(f"{pic}:{transfer}".encode()).hexdigest(), f"{pic:0{HASH_BITS // 4}x}"

    def footage(shot, held, bits_apart, transfer):
        return [rendering(pic, bits_apart, transfer) for pic, times in zip(shot, held) for _ in range(times)]

    a, b = [], []
    made = 0
    while made < frames:
        length = rng.randint(20, 200)
        shot = [picture(dark=rng.random() < 0.1) for _ in range(length)]
        held = [4 if rng.random() < 0.05 else 1 for _ in shot]
        fate = rng.random()
        if fate < 0.08:
            b += footage(shot, held, 0, "b")
        elif fate < 0.11:
            a += footage(shot, held, 0, "a")
        elif fate < 0.30:
            a += footage(shot, held, 0, "a")
            b += footage(shot, held, 12, "b")
        else:
            a += footage(shot, held, 0, "a")
            b += [rendering(pic, 1 if rng.random() < 0.33 else 0, "b")
                  for pic, times in zip(shot, held) for _ in range(times)]
        made += length

    for edition, length, transfer in ((a, frames // 25, "a"), (b, frames // 12, "b")):
        edition += [rendering(picture(dark=rng.random() < 0.3), 0, transfer) for _ in range(length)]
    return a, b
