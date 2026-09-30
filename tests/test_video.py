"""Frames are cut out of a video by their index, and placed by their neighbours."""

import os

import numpy as np
import pytest

from movie_edition_comparer import video
from movie_edition_comparer.algorithms import hash_md5
from movie_edition_comparer.compare_hashes import Frames
from movie_edition_comparer.video import (
    Source, clip_command, cut_differences, extract_frame, extract_frames, frame_filename,
)
from tests.capture import Capture, frame
from tests.test_hash_video import hashed

DISTINCT = list(range(100, 160))
BLACK_AMID_DISTINCT = list(range(100, 110)) + [0] * 10 + list(range(120, 140))


def landmarks(values, indexes):
    return [(i, hash_md5(frame(values[i]))) for i in indexes]


class TestExtractFrame:
    @pytest.mark.parametrize("drift", [0, 3, -3, 5, -5])
    def test_is_the_frame_asked_for_however_the_seek_landed(self, drift):
        got, error = extract_frame(Capture(DISTINCT, drift), 30, landmarks(DISTINCT, [27, 28, 29, 31, 32]))
        assert error == drift
        assert np.array_equal(got, frame(DISTINCT[30]))

    def test_need_not_lie_among_the_landmarks(self):
        got, error = extract_frame(Capture(DISTINCT, 2), 45, landmarks(DISTINCT, [30, 31, 32]))
        assert error == 2
        assert np.array_equal(got, frame(DISTINCT[45]))

    def test_frames_that_repeat_are_placed_by_those_about_them(self):
        got, error = extract_frame(Capture(BLACK_AMID_DISTINCT, 2), 15,
                                   landmarks(BLACK_AMID_DISTINCT, [7, 9, 10, 20, 22]))
        assert error == 2
        assert np.array_equal(got, frame(0))

    def test_says_when_it_could_not_be_placed(self):
        got, error = extract_frame(Capture(DISTINCT, 8), 30, landmarks(DISTINCT, [27, 28, 29, 31, 32]))
        assert error is None
        assert got is not None, "still gives what the seek found"

    def test_says_when_the_landmarks_are_not_in_the_video(self):
        _, error = extract_frame(Capture(DISTINCT), 30, [(28, "no such"), (29, "frames")])
        assert error is None


class TestExtractFrames:
    def test_writes_each_frame_named_by_its_index(self, tmp_path, monkeypatch):
        db = hashed(DISTINCT, 60, tmp_path)
        cap = Capture(DISTINCT, drift=-2)
        monkeypatch.setattr(video.cv2, "VideoCapture", lambda _: cap)
        out = str(tmp_path / "frames")
        extract_frames("film.mkv", [10, 40, 10, -1], out, db, "theatrical")
        assert sorted(os.listdir(out)) == [frame_filename(0), frame_filename(10), frame_filename(40)]
        assert np.array_equal(video.cv2.imread(os.path.join(out, frame_filename(40))), frame(DISTINCT[40]))

    def test_leaves_frames_already_written_alone(self, tmp_path, monkeypatch):
        db = hashed(DISTINCT, 60, tmp_path)
        out = str(tmp_path / "frames")
        cap = Capture(DISTINCT)
        monkeypatch.setattr(video.cv2, "VideoCapture", lambda _: cap)
        extract_frames("film.mkv", [10, 40], out, db, "theatrical")
        again = Capture(DISTINCT)
        monkeypatch.setattr(video.cv2, "VideoCapture", lambda _: again)
        extract_frames("film.mkv", [10, 40, 50], out, db, "theatrical")
        assert again.reads < cap.reads
        assert frame_filename(50) in os.listdir(out)


class TestClipCommand:
    def test_seeks_half_a_frame_before_a_whole_frame_and_counts_from_it(self):
        """Ten seconds before frame 2400 is frame 2160; the seek goes to
        2159.5 frames in, so 2160 is the first frame ffmpeg gives out
        however its time was rounded, and the trim counts from there."""
        command = clip_command("film.mkv", start=2400, count=48, output="clip.mp4", fps=24)
        assert command[command.index("-ss") + 1] == f"{2159.5 / 24:.6f}"
        assert "trim=start_frame=240:end_frame=288" in command[command.index("-vf") + 1]
        assert f"atrim=start={240.5 / 24:.6f}:duration=2.000000" in command[command.index("-af") + 1]

    def test_seeks_no_earlier_than_the_start(self):
        command = clip_command("film.mkv", start=24, count=24, output="clip.mp4", fps=24)
        assert command[command.index("-ss") + 1] == "0.000000"
        assert "trim=start_frame=24:end_frame=48" in command[command.index("-vf") + 1]
        assert "atrim=start=1.000000:" in command[command.index("-af") + 1]


def test_cutting_takes_the_frames_either_side_and_at_each_end(tmp_path, monkeypatch):
    db = hashed(DISTINCT, 60, tmp_path)
    monkeypatch.setattr(video.cv2, "VideoCapture", lambda _: Capture(DISTINCT, drift=1))
    out = str(tmp_path / "out")
    cut_differences(
        [(Frames(20, 3), Frames(20, 0))],
        Source("a.mkv", "theatrical", "theatrical"), Source("b.mkv", "extended", "theatrical"),
        db, out, padding=5, fps=24, trim=False, frames=True, clips=False)
    assert sorted(os.listdir(os.path.join(out, "theatrical"))) == [
        frame_filename(19), frame_filename(20), frame_filename(22), frame_filename(23)]
    assert sorted(os.listdir(os.path.join(out, "extended"))) == [
        frame_filename(19), frame_filename(20)]
