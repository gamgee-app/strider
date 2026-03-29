"""Video trimming and frame extraction utilities."""

import os
import os.path
from datetime import timedelta

from movie_edition_comparer.models import SceneDifference


def _time_to_filename(t: timedelta) -> str:
    return str(t).replace(":", ".")


def _frame_filename(timestamp: timedelta) -> str:
    """Generate a deterministic filename for a frame at a given timestamp."""
    total_ms = int(timestamp.total_seconds() * 1000)
    return f"frame_{total_ms:012d}.png"


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
    timestamp: timedelta, output_dir: str,
):
    import ffmpeg

    filename = f"{output_dir}/{index}-{_time_to_filename(timestamp)}-{identifier}.png"
    if not os.path.isfile(filename):
        (
            ffmpeg
            .input(input_file, ss=timestamp)
            .output(filename, vframes=1)
            .run(quiet=True)
        )


def extract_frames(
    input_file: str, timestamps: list[timedelta],
    output_dir: str, width: int = 320,
):
    """Extract frames at the given timestamps, skipping any that already exist.

    Opens the video once with OpenCV and seeks forward through sorted timestamps,
    avoiding per-frame process overhead.
    """
    import cv2
    from progress.bar import Bar

    os.makedirs(output_dir, exist_ok=True)

    # Deduplicate, clamp to zero, and sort for sequential seeking
    unique_ts = sorted(set(max(ts, timedelta(0)) for ts in timestamps))

    # Filter out already-extracted frames
    to_extract = [
        ts for ts in unique_ts
        if not os.path.isfile(os.path.join(output_dir, _frame_filename(ts)))
    ]

    if not to_extract:
        return

    cap = cv2.VideoCapture(input_file)
    try:
        with Bar("  Extracting", max=len(to_extract)) as bar:
            for ts in to_extract:
                ms = ts.total_seconds() * 1000
                cap.set(cv2.CAP_PROP_POS_MSEC, ms)
                ret, frame = cap.read()
                if ret:
                    # Scale to target width, preserving aspect ratio
                    h, w = frame.shape[:2]
                    if w != width:
                        scale = width / w
                        new_h = int(h * scale)
                        frame = cv2.resize(frame, (width, new_h),
                                           interpolation=cv2.INTER_AREA)
                    out_path = os.path.join(output_dir, _frame_filename(ts))
                    cv2.imwrite(out_path, frame)
                bar.next()
    finally:
        cap.release()


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
            if do_trim:
                trim_video(movie_a, label_a, index,
                           diff.a_range.start - video_padding,
                           diff.a_range.start, output_dir)
                trim_video(movie_a, label_a, index,
                           diff.a_range.end - diff.a_range.duration,
                           diff.a_range.end + video_padding, output_dir)
                trim_video(movie_b, label_b, index,
                           diff.b_range.start - video_padding,
                           diff.b_range.end + video_padding, output_dir)

            if do_frames:
                grab_frame(movie_a, label_a, index, diff.a_range.start, output_dir)
                grab_frame(movie_b, label_b, index, diff.b_range.start, output_dir)
                grab_frame(movie_a, label_a, index, diff.a_range.end, output_dir)
                grab_frame(movie_b, label_b, index, diff.b_range.end, output_dir)

            bar.next()
