"""Tests for the report module's pure logic."""

import os
import sys
from datetime import timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from movie_edition_comparer.report import _sample_timestamps
from movie_edition_comparer.models import TimeRange


class TestSampleTimestamps:
    def test_zero_duration_returns_empty(self):
        tr = TimeRange(timedelta(seconds=10), timedelta(seconds=10))
        assert _sample_timestamps(tr, 5) == []

    def test_zero_count_returns_empty(self):
        tr = TimeRange(timedelta(seconds=0), timedelta(seconds=10))
        assert _sample_timestamps(tr, 0) == []

    def test_single_sample_returns_midpoint(self):
        tr = TimeRange(timedelta(seconds=10), timedelta(seconds=20))
        result = _sample_timestamps(tr, 1)
        assert len(result) == 1
        assert result[0] == timedelta(seconds=15)

    def test_multiple_samples_evenly_spaced(self):
        tr = TimeRange(timedelta(seconds=0), timedelta(seconds=12))
        result = _sample_timestamps(tr, 3)
        assert len(result) == 3
        assert result[0] == timedelta(seconds=3)
        assert result[1] == timedelta(seconds=6)
        assert result[2] == timedelta(seconds=9)

    def test_samples_exclude_endpoints(self):
        tr = TimeRange(timedelta(seconds=5), timedelta(seconds=15))
        result = _sample_timestamps(tr, 4)
        assert all(timedelta(seconds=5) < t < timedelta(seconds=15) for t in result)

    def test_negative_duration_returns_empty(self):
        tr = TimeRange(timedelta(seconds=10), timedelta(seconds=5))
        assert _sample_timestamps(tr, 3) == []
