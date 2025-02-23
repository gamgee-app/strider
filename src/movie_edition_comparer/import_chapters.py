import argparse
import os
import sqlite3
import xml.etree.ElementTree as ET
from contextlib import closing

from progress.bar import Bar


def create_table(db_path: str, table_name: str):
    db_dir = os.path.dirname(db_path)
    os.makedirs(db_dir, exist_ok=True)
    with closing(sqlite3.connect(db_path)) as connection:
        connection.execute(f"""
            CREATE TABLE IF NOT EXISTS {table_name} (
                start_time TEXT PRIMARY KEY,
                title TEXT
            )
        """)


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


def save_chapters_to_table(chapters: list[tuple[str, str]], db_path: str, table_name: str):
    with (closing(sqlite3.connect(db_path)) as connection,
          Bar('Inserting', max=len(chapters)) as bar):
        for chapter in chapters:
            connection.execute(f"""
                INSERT INTO {table_name} (start_time, title)
                VALUES (?, ?)
            """, chapter)
            bar.next()
        connection.commit()


def main():
    parser = argparse.ArgumentParser(
        prog='Import Chapters',
        description='Saves chapter information to a database'
    )

    parser.add_argument('chapters', help="Path to the chapters file")
    parser.add_argument('table', help="Name of the table to save data to")
    parser.add_argument('--db', default="data/frame_hashes.db", help="Path to database file")
    args = parser.parse_args()

    create_table(args.db, args.table)
    chapters = list(read_chapters(args.chapters))
    save_chapters_to_table(chapters, args.db, args.table)


if __name__ == "__main__":
    main()
