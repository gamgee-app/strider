"""Unified CLI entry point for strider."""

import argparse

from movie_edition_comparer.compare_hashes import (
    configure_parser as configure_compare_parser,
    run as run_compare,
)
from movie_edition_comparer.hash_video import (
    configure_parser as configure_hash_parser,
    run as run_hash,
)


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
    configure_hash_parser(hash_parser)

    # --- compare subcommand ---
    compare_parser = subparsers.add_parser(
        "compare",
        help="Compare two hashed editions and report differences",
    )
    configure_compare_parser(compare_parser)

    args = parser.parse_args()

    if args.command == "hash":
        run_hash(args)
    elif args.command == "compare":
        run_compare(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
