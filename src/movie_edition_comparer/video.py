"""Video trimming and frame extraction utilities."""

import os
import os.path
import sys
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

    os.environ["OPENCV_LOG_LEVEL"] = "SILENT"
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


def _anchored_extract(cap, target_idx: int, landmarks: list[tuple[int, str]],
                      max_seek_error: int = 5):
    """Extract a frame using MD5-anchored positioning.

    Seeks to before the landmark region, reads a window of frames, then
    slides the expected MD5 landmarks across the read buffer to find the
    exact seek offset.  Once anchored, returns the frame at target_idx.

    Args:
        cap: OpenCV VideoCapture.
        target_idx: The frame index to extract.
        landmarks: List of (frame_index, expected_md5) with distinct MD5s.
        max_seek_error: Maximum seek drift to test in either direction.

    Returns (frame, seek_error) or (None, 0) on failure.
    """
    from movie_edition_comparer.algorithms import hash_frame_md5

    earliest = min(idx for idx, _ in landmarks)
    latest = max(idx for idx, _ in landmarks)

    # Buffer must cover landmarks and target across all possible seek errors
    buffer_start = min(earliest, target_idx) - max_seek_error
    buffer_end = max(latest, target_idx) + max_seek_error
    buffer_start = max(0, buffer_start)
    read_count = buffer_end - buffer_start + 1

    cap.set(1, buffer_start)  # cv2.CAP_PROP_POS_FRAMES = 1
    frames = []
    for _ in range(read_count):
        ret, frame = cap.read()
        frames.append(frame if ret else None)

    # Try each possible seek error: actual position = buffer_start + error
    # Frame at read position P is actually frame (buffer_start + error + P)
    # So landmark L is at read position (L - buffer_start - error)
    for error in range(-max_seek_error, max_seek_error + 1):
        all_match = True
        for landmark_idx, expected_md5 in landmarks:
            read_pos = landmark_idx - buffer_start - error
            if read_pos < 0 or read_pos >= len(frames) or frames[read_pos] is None:
                all_match = False
                break
            if hash_frame_md5(frames[read_pos]) != expected_md5:
                all_match = False
                break
        if all_match:
            target_pos = target_idx - buffer_start - error
            if 0 <= target_pos < len(frames) and frames[target_pos] is not None:
                return frames[target_pos], error
            break

    # Fallback: no anchor found, return unverified frame at expected position
    fallback_pos = target_idx - buffer_start
    if 0 <= fallback_pos < len(frames) and frames[fallback_pos] is not None:
        return frames[fallback_pos], 0
    return None, 0


def extract_frames(
    input_file: str, frame_indices: list[int],
    output_dir: str,
    db_path: str | None = None,
    edition: str | None = None,
):
    """Extract frames at the given indices, skipping any that already exist.

    When db_path and edition are provided, uses MD5-anchored seeking to
    guarantee correct frame positioning despite HEVC seek inaccuracy.
    """
    import cv2

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

    use_anchoring = db_path is not None and edition is not None
    if use_anchoring:
        from movie_edition_comparer.db import fetch_md5_landmarks

    # Suppress HEVC decoder warnings from OpenCV (noisy on every seek)
    os.environ["OPENCV_LOG_LEVEL"] = "SILENT"

    is_tty = sys.stderr.isatty()
    total = len(to_extract)

    cap = cv2.VideoCapture(input_file)
    try:
        bar = None
        if is_tty:
            from progress.bar import Bar
            bar = Bar("  Extracting", max=total)

        for i, idx in enumerate(to_extract):
            if use_anchoring:
                landmarks = fetch_md5_landmarks(db_path, edition, idx)
                frame, seek_error = _anchored_extract(cap, idx, landmarks)
            else:
                cap.set(1, idx)
                ret, frame = cap.read()
                frame = frame if ret else None
                seek_error = 0
            if frame is not None:
                out_path = os.path.join(output_dir, _frame_filename(idx))
                cv2.imwrite(out_path, frame)

            if bar:
                bar.next()
            elif (i + 1) % 50 == 0 or i + 1 == total:
                print(f"  Extracted {i + 1}/{total} (frame {idx}, seek_error={seek_error})")

        if bar:
            bar.finish()
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

    Uses -ss before -i for fast keyframe seeking, then the trim video
    filter for frame-exact start/end selection. Re-encodes to H.264+AAC
    at 720p for browser playback. Skips if the output file already exists.
    """
    import subprocess

    os.makedirs(output_dir, exist_ok=True)
    out_path = os.path.join(output_dir, _clip_filename(start_frame, end_frame))
    if os.path.isfile(out_path):
        return out_path

    start_time = start_frame / fps
    inner_frames = end_frame - start_frame - 1
    if inner_frames <= 0:
        return out_path

    # Seek to 10s before start for keyframe context, minimum 0
    seek_time = max(0, start_time - 10)

    # trim filter uses frame numbers relative to the input stream,
    # but with -ss the stream starts from the seek point.
    # We need to calculate frame offsets relative to the seek point.
    seek_frame = int(seek_time * fps)
    trim_start = start_frame - seek_frame + 1  # +1 for first inner frame
    trim_end = trim_start + inner_frames

    vf = f"trim=start_frame={trim_start}:end_frame={trim_end},setpts=PTS-STARTPTS,scale=1280:-2"

    # Calculate audio trim relative to seek point
    audio_start = (start_frame + 1) / fps - seek_time
    audio_duration = inner_frames / fps
    af = f"atrim=start={audio_start:.6f}:duration={audio_duration:.6f},asetpts=PTS-STARTPTS"

    subprocess.run(
        [
            "ffmpeg", "-y",
            "-ss", f"{seek_time:.6f}",
            "-i", input_file,
            "-vf", vf,
            "-af", af,
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
