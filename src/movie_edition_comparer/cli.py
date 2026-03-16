"""Unified CLI entry point for strider."""

import argparse

from movie_edition_comparer.hash_video import (
    configure_parser as configure_hash_parser,
    run as run_hash,
)
from movie_edition_comparer.import_chapters import (
    configure_parser as configure_import_chapters_parser,
    run as run_import_chapters,
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
    subparsers.add_parser(
        "compare",
        help="Compare two hashed editions and report differences",
    )

    # --- import-chapters subcommand ---
    import_chapters_parser = subparsers.add_parser(
        "import-chapters",
        help="Import chapter metadata from an XML file",
    )
    configure_import_chapters_parser(import_chapters_parser)

    args = parser.parse_args()

    if args.command == "hash":
        run_hash(args)
    elif args.command == "compare":
        from movie_edition_comparer.compare_hashes import main as compare_main
        compare_main()
    elif args.command == "import-chapters":
        run_import_chapters(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
