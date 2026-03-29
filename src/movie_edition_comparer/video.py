"""Video trimming and frame extraction utilities."""

import os
import os.path
from datetime import timedelta

from movie_edition_comparer.models import SceneDifference


def _time_to_filename(t: timedelta) -> str:
    return str(t).replace(":", ".")


def _frame_filename(frame_index: int) -> str:
    """Generate a deterministic filename for a frame by its index."""
    return f"frame_{frame_index:012d}.png"


def trim_video(
    input_file: str, identifier: str, index: int,
    start: timedelta, end: timedelta, output_dir: str,
) -> str:
    import ffmpeg

    _, ext = os.path.splitext(input_file)
    filename = (
        f"{output_dir}/{index}-"
        f"{_time_to_filename(start)}-{_time_to_filename(end)}-"
        f"{identifier}{ext}"
    )
    if not os.path.isfile(filename):
        (
            ffmpeg
            .input(input_file)
            .output(filename, ss=start, to=end, c="copy")
            .run(quiet=True)
        )
    return filename


def grab_frame(
    input_file: str, identifier: str, index: int,
    frame_index: int, output_dir: str, fps: float,
):
    """Extract a single frame by index using OpenCV."""
    import cv2

    timestamp = timedelta(seconds=frame_index / fps)
    filename = f"{output_dir}/{index}-{_time_to_filename(timestamp)}-{identifier}.png"
    if not os.path.isfile(filename):
        cap = cv2.VideoCapture(input_file)
        try:
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
            ret, frame = cap.read()
            if ret:
                cv2.imwrite(filename, frame)
        finally:
            cap.release()


def extract_frames(
    input_file: str, frame_indices: list[int],
    output_dir: str,
):
    """Extract frames at the given indices, skipping any that already exist.

    Opens the video once with OpenCV and seeks by frame index for exact
    frame extraction. Frames are saved at native resolution.
    """
    import cv2
    from progress.bar import Bar

    os.makedirs(output_dir, exist_ok=True)

    # Deduplicate, clamp to zero, and sort for sequential seeking
    unique_frames = sorted(set(max(idx, 0) for idx in frame_indices))

    # Filter out already-extracted frames
    to_extract = [
        idx for idx in unique_frames
        if not os.path.isfile(os.path.join(output_dir, _frame_filename(idx)))
    ]

    if not to_extract:
        return

    cap = cv2.VideoCapture(input_file)
    try:
        with Bar("  Extracting", max=len(to_extract)) as bar:
            for idx in to_extract:
                cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
                ret, frame = cap.read()
                if ret:
                    out_path = os.path.join(output_dir, _frame_filename(idx))
                    cv2.imwrite(out_path, frame)
                bar.next()
    finally:
        cap.release()


def _clip_filename(start_frame: int, end_frame: int) -> str:
    """Generate a deterministic filename for a clip by its frame range."""
    return f"clip_{start_frame:012d}_{end_frame:012d}.mp4"


def extract_clip(
    input_file: str, start_frame: int, end_frame: int,
    output_dir: str, fps: float,
):
    """Extract a frame-exact clip as 720p H.264 MP4.

    Uses ffmpeg with output-side -ss for frame-exact seeking, then
    re-encodes to H.264+AAC at 720p for browser playback.
    Skips if the output file already exists.
    """
    import subprocess

    os.makedirs(output_dir, exist_ok=True)
    out_path = os.path.join(output_dir, _clip_filename(start_frame, end_frame))
    if os.path.isfile(out_path):
        return out_path

    start_time = start_frame / fps
    duration = (end_frame - start_frame) / fps

    subprocess.run(
        [
            "ffmpeg", "-y",
            "-i", input_file,
            "-ss", f"{start_time:.6f}",
            "-t", f"{duration:.6f}",
            "-vf", "scale=1280:-2",
            "-c:v", "libx264", "-preset", "medium", "-crf", "18",
            "-c:a", "aac", "-b:a", "192k",
            "-movflags", "+faststart",
            out_path,
        ],
        check=True, capture_output=True,
    )
    return out_path


def extract_clips(
    differences: list[SceneDifference],
    movie_a: str, movie_b: str,
    label_a: str, label_b: str,
    clips_dir: str,
):
    """Extract clips for all differences, skipping already-extracted ones."""
    from progress.bar import Bar

    a_clips_dir = os.path.join(clips_dir, label_a)
    b_clips_dir = os.path.join(clips_dir, label_b)

    to_extract = []
    for diff in differences:
        if diff.a_range.inner_count > 0:
            out = os.path.join(a_clips_dir, _clip_filename(diff.a_range.start, diff.a_range.end))
            if not os.path.isfile(out):
                to_extract.append((movie_a, diff.a_range.start, diff.a_range.end, a_clips_dir, diff.fps))
        if diff.b_range.inner_count > 0:
            out = os.path.join(b_clips_dir, _clip_filename(diff.b_range.start, diff.b_range.end))
            if not os.path.isfile(out):
                to_extract.append((movie_b, diff.b_range.start, diff.b_range.end, b_clips_dir, diff.fps))

    if not to_extract:
        return

    with Bar("Extracting clips", max=len(to_extract)) as bar:
        for input_file, start, end, out_dir, fps in to_extract:
            extract_clip(input_file, start, end, out_dir, fps)
            bar.next()


def cut_differences(
    differences: list[SceneDifference],
    movie_a: str, movie_b: str,
    label_a: str, label_b: str,
    output_dir: str, padding: float,
    do_trim: bool = True, do_frames: bool = True,
):
    from progress.bar import Bar

    video_padding = timedelta(seconds=padding)
    with Bar("Cutting", max=len(differences)) as bar:
        for index, diff in enumerate(differences):
            a_start = diff.to_time(diff.a_range.start)
            a_end = diff.to_time(diff.a_range.end)
            b_start = diff.to_time(diff.b_range.start)
            b_end = diff.to_time(diff.b_range.end)

            if do_trim:
                trim_video(movie_a, label_a, index,
                           a_start - video_padding,
                           a_start, output_dir)
                trim_video(movie_a, label_a, index,
                           a_end - timedelta(seconds=diff.a_range.frame_count / diff.fps),
                           a_end + video_padding, output_dir)
                trim_video(movie_b, label_b, index,
                           b_start - video_padding,
                           b_end + video_padding, output_dir)

            if do_frames:
                grab_frame(movie_a, label_a, index, diff.a_range.start, output_dir, diff.fps)
                grab_frame(movie_b, label_b, index, diff.b_range.start, output_dir, diff.fps)
                grab_frame(movie_a, label_a, index, diff.a_range.end, output_dir, diff.fps)
                grab_frame(movie_b, label_b, index, diff.b_range.end, output_dir, diff.fps)

            bar.next()
