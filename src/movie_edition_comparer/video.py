"""Cutting frames and clips out of an edition's video.

Seeking a video is not exact: a seek lands a few frames either side of
where it was asked to. A frame wanted by its index is placed by the frames
about it that are already hashed, the way hash_video finds where it left
off, so what is cut is the frame that was reported and not one near it.
"""

import os
import subprocess
from dataclasses import dataclass
from datetime import timedelta

import cv2
import ffmpeg
from numpy import ndarray
from progress.bar import Bar

from movie_edition_comparer.algorithms import hash_md5
from movie_edition_comparer.db import landmarks_near
from movie_edition_comparer.hash_video import MAX_SEEK_ERROR, seek_error


@dataclass(frozen=True)
class Source:
    """One edition's video, and what to call it."""
    video: str
    label: str
    edition: str


# --- frames ------------------------------------------------------------------

def frame_filename(index: int) -> str:
    return f"frame_{index:012d}.png"


def extract_frame(cap, target: int, landmarks: list[tuple[int, str]],
                  max_error: int = MAX_SEEK_ERROR) -> tuple[ndarray | None, int | None]:
    """The frame at target, placed by the landmarks about it.

    Reads a stretch wide enough to hold the landmarks and the target
    however far the seek lands, and takes the frame that sits at the target
    once the landmarks say how far off it was. Given back with how far off
    that was -- or None, when the landmarks could not be found and the frame
    is whatever the seek happened to give.
    """
    indexes = [index for index, _ in landmarks] + [target]
    first = max(0, min(indexes) - max_error)
    last = max(indexes) + max_error

    cap.set(cv2.CAP_PROP_POS_FRAMES, first)
    frames = []
    for _ in range(last - first + 1):
        ret, frame = cap.read()
        frames.append(frame if ret else None)

    # Only the places a landmark could have been read need hashing.
    could_be = {index - first - error
                for index, _ in landmarks
                for error in range(-max_error, max_error + 1)}
    md5s = [hash_md5(frame) if place in could_be and frame is not None else None
            for place, frame in enumerate(frames)]

    error = seek_error(md5s, first, landmarks, max_error)
    place = target - first - (error or 0)
    return (frames[place] if 0 <= place < len(frames) else None), error


def extract_frames(video: str, indexes: list[int], output_dir: str,
                   db_path: str | None = None, edition: str | None = None) -> None:
    """Write the frames at these indexes as PNGs, skipping any already there.

    Placed by their neighbours when the edition's database is given;
    otherwise wherever the seek lands.
    """
    os.makedirs(output_dir, exist_ok=True)
    wanted = sorted(index for index in {max(0, index) for index in indexes}
                    if not os.path.isfile(os.path.join(output_dir, frame_filename(index))))
    if not wanted:
        return

    os.environ.setdefault("OPENCV_LOG_LEVEL", "SILENT")
    cap = cv2.VideoCapture(video)
    try:
        with Bar("Frames", max=len(wanted)) as bar:
            for index in wanted:
                if db_path and edition:
                    frame, error = extract_frame(cap, index, landmarks_near(db_path, edition, index))
                    if error is None:
                        print(f"\nFrame {index} could not be placed; saved as the seek found it")
                else:
                    cap.set(cv2.CAP_PROP_POS_FRAMES, index)
                    ret, frame = cap.read()
                    frame = frame if ret else None
                if frame is not None:
                    cv2.imwrite(os.path.join(output_dir, frame_filename(index)), frame)
                bar.next()
    finally:
        cap.release()


# --- clips -------------------------------------------------------------------

def _filename_time(time: timedelta) -> str:
    return str(time).replace(":", ".")


def trim_video(video: str, label: str, index: int,
               start: timedelta, end: timedelta, output_dir: str) -> str:
    """A stretch of the video between two times, copied as it is.

    Cut on keyframes, so it starts a little before and ends a little after,
    but with the picture and sound untouched.
    """
    _, extension = os.path.splitext(video)
    filename = f"{output_dir}/{index}-{_filename_time(start)}-{_filename_time(end)}-{label}{extension}"
    if not os.path.isfile(filename):
        (
            ffmpeg
            .input(video)
            .output(filename, ss=start, to=end, c="copy")
            .run(quiet=True)
        )
    return filename


def clip_filename(start: int, count: int) -> str:
    return f"clip_{start:012d}_{start + count:012d}.mp4"


def clip_command(video: str, start: int, count: int, output: str, fps: float) -> list[str]:
    """The ffmpeg invocation for a clip of exactly these frames, at 720p.

    Seeks to some seconds before the first frame so the decoder has a
    keyframe to start from, then trims to the frames wanted counting from
    the first frame delivered, and takes the same stretch of sound.

    Seeking is exact in time, not in frames: ffmpeg decodes from the
    keyframe before the time asked for and gives out the first frame at or
    after it. So the seek goes half a frame before a whole frame, and that
    frame is the first delivered whatever the container rounded its time
    to, and the trim counts from it.
    """
    seek_frame = max(0, start - round(10 * fps))
    seek_time = max(0.0, (seek_frame - 0.5) / fps)
    first, last = start - seek_frame, start - seek_frame + count
    sound_from = start / fps - seek_time
    return [
        "ffmpeg", "-y",
        "-ss", f"{seek_time:.6f}",
        "-i", video,
        "-vf", f"trim=start_frame={first}:end_frame={last},setpts=PTS-STARTPTS,scale=1280:-2",
        "-af", f"atrim=start={sound_from:.6f}:duration={count / fps:.6f},asetpts=PTS-STARTPTS",
        "-c:v", "libx264", "-preset", "medium", "-crf", "18",
        "-c:a", "aac", "-b:a", "192k",
        "-movflags", "+faststart",
        output,
    ]


def extract_clip(video: str, start: int, count: int, output_dir: str, fps: float) -> str:
    """A clip of exactly the count frames from start, re-encoded at 720p."""
    os.makedirs(output_dir, exist_ok=True)
    output = os.path.join(output_dir, clip_filename(start, count))
    if count > 0 and not os.path.isfile(output):
        subprocess.run(clip_command(video, start, count, output, fps), check=True, capture_output=True)
    return output


# --- everything reported -----------------------------------------------------

def cut_differences(pairs, a: Source, b: Source, db_path: str, output_dir: str,
                    padding: float, fps: float,
                    trim: bool, frames: bool, clips: bool) -> None:
    """Cut what was reported out of both videos.

    Each pair is a stretch of frames in edition a and the stretch it
    answers to in edition b, either of which may be empty. For each: the
    stretch and some padding copied out as it is, the frames either side of
    it and at each end of it, and a clip of exactly its frames.
    """
    def time(frame: int) -> timedelta:
        return timedelta(seconds=frame / fps)

    def edges(stretch) -> list[int]:
        """The frame before, the first, the last, and the frame after."""
        return [stretch.start - 1, stretch.start,
                stretch.start + stretch.count - 1, stretch.start + stretch.count]

    os.makedirs(output_dir, exist_ok=True)
    video_padding = timedelta(seconds=padding)

    if trim:
        with Bar("Cutting", max=len(pairs)) as bar:
            for index, (a_frames, b_frames) in enumerate(pairs):
                a_start, a_end = time(a_frames.start), time(a_frames.start + max(0, a_frames.count - 1))
                b_start, b_end = time(b_frames.start), time(b_frames.start + max(0, b_frames.count - 1))
                trim_video(a.video, a.label, index, a_start - video_padding, a_start, output_dir)
                trim_video(a.video, a.label, index, a_start, a_end + video_padding, output_dir)
                trim_video(b.video, b.label, index, b_start - video_padding, b_end + video_padding, output_dir)
                bar.next()

    if frames:
        for source, side in ((a, 0), (b, 1)):
            extract_frames(source.video, [index for pair in pairs for index in edges(pair[side])],
                           os.path.join(output_dir, source.label), db_path, source.edition)

    if clips:
        for source, side in ((a, 0), (b, 1)):
            stretches = [pair[side] for pair in pairs if pair[side].count > 0]
            with Bar(f"Clips of {source.label}", max=len(stretches)) as bar:
                for stretch in stretches:
                    extract_clip(source.video, stretch.start, stretch.count,
                                 os.path.join(output_dir, source.label), fps)
                    bar.next()
