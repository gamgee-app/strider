import argparse
import sqlite3
import xml.etree.ElementTree as ET
from contextlib import closing

from movie_edition_comparer.db import create_database, write_chapters


def read_chapters(chapters) -> list[tuple[str, str]]:
    tree = ET.parse(chapters)
    root = tree.getroot()

    if root.tag != 'Chapters':
        raise Exception('Expected XML document with root element Chapters')

    edition_entry = root.find('EditionEntry')
    if not edition_entry:
        raise Exception('Expected XML tag EditionEntry under Chapters')

    for chapter in edition_entry.findall('ChapterAtom'):
        chapter_display = chapter.find('ChapterDisplay')
        if not chapter_display:
            raise Exception('Expected XML tag ChapterDisplay for ChapterAtom')

        time_start = chapter.findtext('ChapterTimeStart')
        title = chapter_display.findtext('ChapterString')
        yield time_start, title


def main():
    parser = argparse.ArgumentParser(
        prog='Import Chapters',
        description='Saves chapter information to a database'
    )

    parser.add_argument('chapters', help="Path to the chapters file")
    parser.add_argument('--edition', required=True, help="Name of the edition, e.g. theatrical")
    parser.add_argument('--db', required=True, help="Path to the film's database, e.g. data/two_towers.db")
    args = parser.parse_args()

    create_database(args.db)
    chapters = list(read_chapters(args.chapters))
    with closing(sqlite3.connect(args.db)) as connection:
        write_chapters(connection, args.edition, chapters)
        connection.commit()
    print(f"Imported {len(chapters)} chapters")


if __name__ == "__main__":
    main()
