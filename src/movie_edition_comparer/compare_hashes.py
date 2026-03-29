"""CLI entry point for comparing movie edition hashes."""

import argparse
from datetime import timedelta

from movie_edition_comparer.comparison import find_all_differences
from movie_edition_comparer.db import make_db_fetcher, read_unique_matches
from movie_edition_comparer.models import ComparisonConfig, SceneDifference
from movie_edition_comparer.video import cut_differences


def configure_parser(parser: argparse.ArgumentParser):
    """Add compare arguments to an argument parser."""
    parser.add_argument("--edition-a", required=True, help="Edition name for edition A (e.g. 'theatrical')")
    parser.add_argument("--edition-b", required=True, help="Edition name for edition B (e.g. 'extended')")
    parser.add_argument("--db", default="data/frame_hashes.db", help="Path to database file")
    parser.add_argument("--label-a", default="a", help="Short label for edition A (used in filenames)")
    parser.add_argument("--label-b", default="b", help="Short label for edition B (used in filenames)")
    parser.add_argument("--movie-a", default=None, help="Path to edition A video file (enables trimming/frames)")
    parser.add_argument("--movie-b", default=None, help="Path to edition B video file (enables trimming/frames)")
    parser.add_argument("--output-dir", default="out", help="Directory for output clips and frames")
    parser.add_argument("--json", action="store_true", help="Print difference ranges as JSON")
    parser.add_argument("--no-trim", action="store_true", help="Skip trimming video clips")
    parser.add_argument("--no-frames", action="store_true", help="Skip grabbing reference frames")
    parser.add_argument("--padding", type=float, default=5, help="Seconds of padding around video clips")
    parser.add_argument("--report", default=None, metavar="FILE", help="Generate an HTML visual verification report")
    parser.add_argument("--contact-frames", type=int, default=8, help="Frames per contact sheet in the report (default: 8)")
    parser.add_argument("--frames-dir", default="frames", help="Directory for extracted report frames (default: frames)")


def run(args):
    """Run the compare command with parsed arguments."""
    from tabulate import tabulate

    config = ComparisonConfig()

    print("Reading unique matches…")
    all_matches = read_unique_matches(args.db, args.edition_a, args.edition_b)
    a_fetcher = make_db_fetcher(args.db, args.edition_a)
    b_fetcher = make_db_fetcher(args.db, args.edition_b)

    print("Finding differences…")
    differences = find_all_differences(all_matches, a_fetcher, b_fetcher, config)

    def sort_key(d: SceneDifference) -> int:
        return max(d.a_range.frame_count, d.b_range.frame_count)

    sorted_diffs = sorted(differences, key=sort_key)

    tabulated = tabulate(
        [(
            d.to_time(d.a_range.start), d.to_time(d.a_range.end), d.difference_type,
            d.to_time(d.b_range.start), d.to_time(d.b_range.end), d.difference_type,
            timedelta(seconds=d.a_range.frame_count / d.fps),
            timedelta(seconds=d.b_range.frame_count / d.fps),
            d.duration_difference,
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

    if args.json:
        import json
        for attr in ["a_range", "b_range"]:
            ranges = [
                {
                    "start_time": str(d.to_time(getattr(d, attr).start)),
                    "end_time": str(d.to_time(getattr(d, attr).end)),
                    "type": d.difference_type,
                }
                for d in differences
                if getattr(d, attr).frame_count > 0
            ]
            print(json.dumps(ranges))

    if args.report and args.movie_a and args.movie_b:
        from movie_edition_comparer.report import generate_report
        generate_report(
            sorted_diffs, args.movie_a, args.movie_b,
            args.label_a, args.label_b, args.report,
            frames_dir=args.frames_dir,
            contact_frames=args.contact_frames,
        )

    do_trim = not args.no_trim and args.movie_a and args.movie_b
    do_frames = not args.no_frames and args.movie_a and args.movie_b

    if do_trim or do_frames:
        print()
        cut_differences(
            sorted_diffs,
            args.movie_a, args.movie_b,
            args.label_a, args.label_b,
            args.output_dir, args.padding,
            do_trim=bool(do_trim), do_frames=bool(do_frames),
        )


def main():
    parser = argparse.ArgumentParser(
        prog="strider compare",
        description="Compare two hashed movie editions and report differences",
    )
    configure_parser(parser)
    args = parser.parse_args()
    run(args)


if __name__ == "__main__":
    main()
