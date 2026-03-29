"""Data models for movie edition comparison."""

from dataclasses import dataclass
from datetime import timedelta
from typing import Callable


@dataclass(frozen=True)
class ComparisonConfig:
    """Configuration parameters for hash comparison."""
    fps: float = 23.976216
    perceptual_match_threshold: float = 5.0
    extended_similarity_threshold: int = 12
    maximum_inter_match_search: int = 24
    boundary_gap_tolerance: int = 1
    boundary_gap_max_distance: float = 10.0


@dataclass(frozen=True)
class FrameHash:
    """A frame index paired with its hash value."""
    index: int
    hash: str


@dataclass(frozen=True)
class FrameMatch:
    """A pair of frames (one from each edition) with matching hashes."""
    a: FrameHash
    b: FrameHash


class DifferenceType:
    UNIQUE_TO_A = "unique_to_a"
    UNIQUE_TO_B = "unique_to_b"
    MODIFIED = "modified"
    REORDERED = "reordered"


@dataclass(frozen=True)
class FrameRange:
    """A range of frame indices within a video.

    start and end are the boundary match frame indices (the last matching
    frame before the difference and the first matching frame after).
    """
    start: int
    end: int

    @property
    def frame_count(self) -> int:
        """Total frames spanned including boundary matches."""
        return max(0, self.end - self.start)

    @property
    def inner_count(self) -> int:
        """Number of differing frames between the boundary matches."""
        return max(0, self.end - self.start - 1)


def frame_to_time(frame: int, fps: float) -> timedelta:
    """Convert a frame index to a timedelta timestamp."""
    return timedelta(seconds=frame / fps)


@dataclass(frozen=True)
class SceneDifference:
    """A detected difference between two movie editions."""
    a_range: FrameRange
    b_range: FrameRange
    difference_type: str
    fps: float = 23.976216
    start_match: FrameMatch | None = None
    end_match: FrameMatch | None = None
    first_inner_a: FrameHash | None = None
    first_inner_b: FrameHash | None = None
    last_inner_a: FrameHash | None = None
    last_inner_b: FrameHash | None = None

    def to_time(self, frame: int) -> timedelta:
        """Convert a frame index to a timedelta using this difference's fps."""
        return frame_to_time(frame, self.fps)

    @property
    def duration_difference(self) -> timedelta:
        a_dur = self.a_range.inner_count / self.fps
        b_dur = self.b_range.inner_count / self.fps
        return timedelta(seconds=abs(b_dur - a_dur))


# Type alias: given (start_index_inclusive, end_index_exclusive), returns frame hashes
HashFetcher = Callable[[int, int], list[FrameHash]]
