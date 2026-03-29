"""Tests for the report module's pure logic."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from movie_edition_comparer.report import _sample_frames
from movie_edition_comparer.models import FrameRange


class TestSampleFrames:
    def test_zero_duration_returns_empty(self):
        fr = FrameRange(10, 10)
        assert _sample_frames(fr, 5) == []

    def test_zero_count_returns_empty(self):
        fr = FrameRange(0, 10)
        assert _sample_frames(fr, 0) == []

    def test_single_sample_returns_midpoint(self):
        fr = FrameRange(10, 20)
        result = _sample_frames(fr, 1)
        assert len(result) == 1
        assert result[0] == 15

    def test_multiple_samples_evenly_spaced(self):
        fr = FrameRange(0, 12)
        result = _sample_frames(fr, 3)
        assert len(result) == 3
        assert all(0 < f < 12 for f in result)

    def test_samples_exclude_endpoints(self):
        fr = FrameRange(5, 15)
        result = _sample_frames(fr, 4)
        assert all(5 < f < 15 for f in result)

    def test_negative_duration_returns_empty(self):
        fr = FrameRange(10, 5)
        assert _sample_frames(fr, 3) == []
