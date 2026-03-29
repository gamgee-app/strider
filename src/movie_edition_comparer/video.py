"""Video trimming and frame extraction utilities."""

import os.path
from datetime import timedelta

from movie_edition_comparer.models import SceneDifference


def _time_to_filename(t: timedelta) -> str:
    return str(t).replace(":", ".")


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
