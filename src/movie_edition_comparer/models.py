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
class TimeRange:
    """A time range within a video."""
    start: timedelta
    end: timedelta

    @property
    def duration(self) -> timedelta:
        return self.end - self.start


@dataclass(frozen=True)
class SceneDifference:
    """A detected difference between two movie editions."""
    a_range: TimeRange
    b_range: TimeRange
    difference_type: str
    fps: float = 23.976216
    start_match: FrameMatch | None = None
    end_match: FrameMatch | None = None
    first_inner_a: FrameHash | None = None
    first_inner_b: FrameHash | None = None
    last_inner_a: FrameHash | None = None
    last_inner_b: FrameHash | None = None

    @property
    def duration_difference(self) -> timedelta:
        return abs(self.b_range.duration - self.a_range.duration)


# Type alias: given (start_index_inclusive, end_index_exclusive), returns frame hashes
HashFetcher = Callable[[int, int], list[FrameHash]]
