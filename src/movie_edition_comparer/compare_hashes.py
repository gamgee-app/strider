"""CLI entry point for comparing movie edition hashes."""

import os.path
from datetime import timedelta

from movie_edition_comparer.comparison import find_all_differences
from movie_edition_comparer.db import make_db_fetcher, read_unique_matches
from movie_edition_comparer.models import ComparisonConfig, SceneDifference


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


def main():
    import json

    from progress.bar import Bar
    from tabulate import tabulate

    db_path = "data/frame_hashes.db"

    label_a = "theatrical"
    table_a = "two_towers_theatrical"
    movie_a = (
        r"C:\Users\obroo\Lord of the Rings"
        r"\The Lord of the Rings The Two Towers (2002) Theatrical Remux-2160p HDR.mkv"
    )

    label_b = "extended"
    table_b = "two_towers_extended"
    movie_b = (
        r"C:\Users\obroo\Lord of the Rings"
        r"\The Lord of the Rings The Two Towers (2002) Extended Remux-2160p HDR.mkv"
    )

    output_dir = "out"
    print_json = False
    trim_videos = True
    grab_frames = True
    video_padding_seconds = 5
    config = ComparisonConfig()

    print("Reading unique matches…")
    all_matches = read_unique_matches(db_path, table_a, table_b)
    a_fetcher = make_db_fetcher(db_path, table_a)
    b_fetcher = make_db_fetcher(db_path, table_b)

    print("Finding differences…")
    differences = find_all_differences(all_matches, a_fetcher, b_fetcher, config)

    def sort_key(d: SceneDifference) -> timedelta:
        return max(d.a_range.duration, d.b_range.duration)

    sorted_diffs = sorted(differences, key=sort_key)

    tabulated = tabulate(
        [(
            d.a_range.start, d.a_range.end, d.difference_type,
            d.b_range.start, d.b_range.end, d.difference_type,
            d.a_range.duration, d.b_range.duration, d.duration_difference,
        ) for d in sorted_diffs],
        headers=[
            "A Start", "A End", "A Type",
            "B Start", "B End", "B Type",
            "A Duration", "B Duration", "Duration Diff",
        ],
        tablefmt="github",
    )

    print()
    print(f"Count ({len(sorted_diffs)}):")
    print()
    print(tabulated)

    if print_json:
        for label, attr in [("a", "a_range"), ("b", "b_range")]:
            ranges = [
                {
                    "start_time": str(getattr(d, attr).start),
                    "end_time": str(getattr(d, attr).end),
                    "type": d.difference_type,
                }
                for d in differences
                if getattr(d, attr).duration > timedelta(0)
            ]
            print(json.dumps(ranges))

    if trim_videos or grab_frames:
        print()
        video_padding = timedelta(seconds=video_padding_seconds)
        with Bar("Cutting", max=len(sorted_diffs)) as bar:
            for index, diff in enumerate(sorted_diffs):
                if trim_videos:
                    trim_video(movie_a, label_a, index,
                               diff.a_range.start - video_padding,
                               diff.a_range.start, output_dir)
                    trim_video(movie_a, label_a, index,
                               diff.a_range.end - diff.a_range.duration,
                               diff.a_range.end + video_padding, output_dir)
                    trim_video(movie_b, label_b, index,
                               diff.b_range.start - video_padding,
                               diff.b_range.end + video_padding, output_dir)

                if grab_frames:
                    grab_frame(movie_a, label_a, index, diff.a_range.start, output_dir)
                    grab_frame(movie_b, label_b, index, diff.b_range.start, output_dir)
                    grab_frame(movie_a, label_a, index, diff.a_range.end, output_dir)
                    grab_frame(movie_b, label_b, index, diff.b_range.end, output_dir)

                bar.next()


if __name__ == "__main__":
    main()
