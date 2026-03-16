"""Unified CLI entry point for strider."""

import argparse


def main():
    parser = argparse.ArgumentParser(
        prog="strider",
        description="Compare different editions of movies by frame hashing",
    )
    subparsers = parser.add_subparsers(dest="command")

    # --- hash subcommand ---
    hash_parser = subparsers.add_parser(
        "hash",
        help="Hash video frames and store results in a database",
    )
    hash_parser.add_argument("video", help="Path to the video file")
    hash_parser.add_argument("table", help="Name of the table to save data to")
    hash_parser.add_argument("--db", default="data/frame_hashes.db", help="Path to database file")
    hash_parser.add_argument("--threads", default=4, type=int, help="Number of threads to use")

    # --- compare subcommand ---
    subparsers.add_parser(
        "compare",
        help="Compare two hashed editions and report differences",
    )

    args = parser.parse_args()

    if args.command == "hash":
        from hash_video import create_database, hash_video_frames_to_db
        from datetime import datetime

        start_time = datetime.now()
        create_database(args.db, args.table)
        hash_video_frames_to_db(args.video, args.db, args.table, args.threads)
        print(f"Took {datetime.now() - start_time}")

    elif args.command == "compare":
        from compare_hashes import main as compare_main
        compare_main()

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
