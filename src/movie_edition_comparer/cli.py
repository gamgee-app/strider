"""The strider command: hash each edition of a film, average its pictures, then compare two of them."""

import argparse

from movie_edition_comparer import average_video, compare_hashes, hash_video


def main():
    parser = argparse.ArgumentParser(
        prog="strider",
        description="Compare two editions of a film, frame by frame")
    commands = parser.add_subparsers(required=True, metavar="command")

    hash_parser = commands.add_parser(
        "hash", help="Hash every frame of an edition into the film's database")
    hash_video.configure_parser(hash_parser)
    hash_parser.set_defaults(run=hash_video.run)

    average_parser = commands.add_parser(
        "average", help="Keep the block averages of every frame's picture, bars cut away")
    average_video.configure_parser(average_parser)
    average_parser.set_defaults(run=average_video.run)

    compare_parser = commands.add_parser(
        "compare", help="Report where two hashed editions differ")
    compare_hashes.configure_parser(compare_parser)
    compare_parser.set_defaults(run=compare_hashes.run)

    args = parser.parse_args()
    args.run(args)


if __name__ == "__main__":
    main()
