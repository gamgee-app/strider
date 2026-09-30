"""A stand-in for a video, for tests that seek one."""

import numpy as np

CAP_PROP_POS_FRAMES, CAP_PROP_FRAME_COUNT = 1, 7


def frame(value: int) -> np.ndarray:
    """A 2x2 picture whose pixels spell out a number."""
    picture = np.zeros((2, 2, 3), dtype=np.uint8)
    picture[0, 0] = (value & 0xFF, (value >> 8) & 0xFF, (value >> 16) & 0xFF)
    return picture


class Capture:
    """A video whose frames are numbers, and whose seeking is off by a bit.

    Asked to seek to n, it lands at n + drift, as a real decoder does --
    except at the very start of the video, which is always found exactly.
    """

    def __init__(self, values: list[int], drift: int = 0):
        self.values = values
        self.drift = drift
        self.position = 0
        self.reads = 0

    def get(self, prop):
        assert prop == CAP_PROP_FRAME_COUNT
        return len(self.values)

    def set(self, prop, value):
        assert prop == CAP_PROP_POS_FRAMES
        self.position = int(value) + self.drift if value else 0

    def read(self):
        self.reads += 1
        if 0 <= self.position < len(self.values):
            self.position += 1
            return True, frame(self.values[self.position - 1])
        self.position += 1
        return False, None

    def release(self):
        pass
