import datetime
import json
import os.path
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import timedelta

import cv2
import ffmpeg
from progress.bar import Bar
from tabulate import tabulate

from algorithms import deserialize


@dataclass
class HashIndex:
    index: int
    hash: str


def read_hashes_index(db_path: str, table_name: str, lower_index: int, upper_index: int) -> list[HashIndex]:
    with closing(sqlite3.connect(db_path)) as connection:
        cursor = connection.cursor()
        cursor.execute(f"""
            SELECT 
                frame_index,
                hash_block_mean_0
            FROM
                {table_name}
            WHERE
                frame_index >= {lower_index}
                and frame_index < {upper_index}
        """)
        rows = cursor.fetchall()
        return [HashIndex(*row) for row in rows]


@dataclass
class HashMatch:
    a: HashIndex
    b: HashIndex


def read_unique_valid_matches(db_path: str, table_a_name: str, table_b_name: str) -> list[HashMatch]:
    with closing(sqlite3.connect(db_path)) as connection:
        cursor = connection.cursor()
        cursor.execute(f"""
            with a_unique as
                     (select hash_block_mean_0 as perceptual_hash
                      from {table_a_name}
                      group by perceptual_hash
                      having count(1) = 1),
                 b_unique as
                     (select hash_block_mean_0 as perceptual_hash
                      from {table_b_name}
                      group by perceptual_hash
                      having count(1) = 1),
                 unique_matches as
                     (select perceptual_hash
                      from a_unique
                      intersect
                      select perceptual_hash
                      from b_unique),
                 matched_indexes as
                     (select {table_a_name}.frame_index       as a_index,
                             {table_a_name}.hash_block_mean_0 as a_perceptual_hash,
                             {table_b_name}.frame_index       as b_index,
                             {table_b_name}.hash_block_mean_0 as b_perceptual_hash
                      from {table_a_name}
                               join {table_b_name}
                                    on {table_a_name}.hash_block_mean_0 = {table_b_name}.hash_block_mean_0
                      where {table_a_name}.hash_block_mean_0 in unique_matches),
                 invalid_orderings as
                     (select *
                      from (select b_index                              as curr_b_index,
                                   LAG(b_index) over (order by a_index) as prev_b_index
                            from matched_indexes)
                      where curr_b_index < prev_b_index)
            
            select a_index, a_perceptual_hash, b_index, b_perceptual_hash
            from matched_indexes
            where matched_indexes.b_index not in
                  (select curr_b_index
                   from invalid_orderings
                   union
                   select prev_b_index
                   from invalid_orderings)
            order by a_index
        """)
        rows = cursor.fetchall()
        matches = []
        for row in rows:
            a_index, a_perceptual_hash, b_index, b_perceptual_hash = row
            a = HashIndex(a_index, a_perceptual_hash)
            b = HashIndex(b_index, b_perceptual_hash)
            matches.append(HashMatch(a, b))
        return matches


def frame_to_time(frame: int) -> timedelta:
    return datetime.timedelta(seconds=frame / fps)


def get_filename_time(time: timedelta) -> str:
    return str(time).replace(":", ".")


def trim_video(input_file: str, identifier: str, index: int, start: timedelta, end: timedelta) -> str:
    _, input_file_extension = os.path.splitext(input_file)
    filename = f"{output_dir}/{index}-{get_filename_time(start)}-{get_filename_time(end)}-{identifier}{input_file_extension}"
    if not os.path.isfile(filename):
        (
            ffmpeg
            .input(input_file)
            .output(filename, ss=start, to=end, c="copy")
            .run(quiet=True)
        )
    return filename


def grab_frame(input_file: str, identifier: str, index: int, timestamp: timedelta):
    filename = f"{output_dir}/{index}-{get_filename_time(timestamp)}-{identifier}.png"
    if not os.path.isfile(filename):
        (
            ffmpeg
            .input(input_file, ss=timestamp)
            .output(filename, vframes=1)
            .run(quiet=True)
        )


def hamming_distance(hash_a: str, hash_b: str) -> float:
    array_a = deserialize(hash_a)
    array_b = deserialize(hash_b)
    return cv2.norm(array_a, array_b, cv2.NORM_HAMMING)


def count_leading(float_list: list[float], threshold: float) -> int:
    for i, num in enumerate(float_list):
        if num > threshold:
            return i
    return len(float_list)


@dataclass
class HashRange:
    start: timedelta
    end: timedelta
    range: timedelta
    type: str


@dataclass
class HashDifference:
    a_range: HashRange
    b_range: HashRange
    range_difference: timedelta


def match(db_path: str,
          table_a_name: str, table_b_name: str,
          current_match: HashMatch, previous_match: HashMatch) -> HashDifference | None:
    previous_lag = previous_match.b.index - previous_match.a.index
    current_lag = current_match.b.index - current_match.a.index
    lag_difference = current_lag - previous_lag

    if lag_difference < 1:
        return None

    a_start = frame_to_time(previous_match.a.index)
    a_end = frame_to_time(current_match.a.index - 1)
    a_index_range = current_match.a.index - 1 - previous_match.a.index
    a_range = frame_to_time(a_index_range)

    if a_range.total_seconds() < 0:
        # hacky, but fixes a bug, TODO fix cause
        return None

    b_start = frame_to_time(previous_match.b.index)
    b_end = frame_to_time(current_match.b.index - 1)
    b_index_range = current_match.b.index - 1 - previous_match.b.index
    b_range = frame_to_time(b_index_range)

    if b_range.total_seconds() < 0:
        # hacky, but fixes a bug, TODO fix cause
        return None

    a_hashes = read_hashes_index(db_path, table_a_name, previous_match.a.index + 1, current_match.a.index)
    b_hashes = read_hashes_index(db_path, table_b_name, previous_match.b.index + 1, current_match.b.index)

    # check if we only have frames added to b, and those frames are visually similar to its surrounding frames
    if a_index_range == 0 and b_index_range > 0 and b_index_range < extended_similarity_threshold:
        b_hashes_compared_to_previous = [hamming_distance(previous_match.b.hash, b.hash) for b in b_hashes]
        b_hashes_compared_to_current = [hamming_distance(current_match.b.hash, b.hash) for b in b_hashes]
        if min(max(b_hashes_compared_to_previous), max(b_hashes_compared_to_current)) <= perceptual_match_threshold:
            return None

    # check if we only have frames added to a, and those frames are visually similar to its surrounding frames
    if b_index_range == 0 and a_index_range > 0 and a_index_range < extended_similarity_threshold:
        a_hashes_compared_to_previous = [hamming_distance(previous_match.a.hash, a.hash) for a in a_hashes]
        a_hashes_compared_to_current = [hamming_distance(current_match.a.hash, a.hash) for a in a_hashes]
        if min(max(a_hashes_compared_to_previous), max(a_hashes_compared_to_current)) <= perceptual_match_threshold:
            return None

    a_start_hashes = [a.hash for a in a_hashes[:maximum_inter_match_search]]
    a_end_hashes = [a.hash for a in a_hashes[:-1 - maximum_inter_match_search:-1]]
    b_start_hashes = [b.hash for b in b_hashes[:maximum_inter_match_search]]
    b_end_hashes = [b.hash for b in b_hashes[:-1 - maximum_inter_match_search:-1]]

    start_distances = [hamming_distance(a, b) for a, b in zip(a_start_hashes, b_start_hashes)]
    end_distances = [hamming_distance(a, b) for a, b in zip(a_end_hashes, b_end_hashes)]

    start_matches = count_leading(start_distances, perceptual_match_threshold)
    end_matches = count_leading(end_distances, perceptual_match_threshold)

    if start_matches > 0 or end_matches > 0:
        new_previous_a_match = a_hashes[start_matches - 1]
        new_previous_b_match = b_hashes[start_matches - 1]
        new_current_a_match = a_hashes[0 - end_matches]
        new_current_b_match = b_hashes[0 - end_matches]
        new_previous_match = previous_match if start_matches == 0 else HashMatch(new_previous_a_match,
                                                                                 new_previous_b_match)
        new_current_match = current_match if end_matches == 0 else HashMatch(new_current_a_match, new_current_b_match)
        return match(db_path, table_a_name, table_b_name, new_current_match, new_previous_match)

    a_hash_range = HashRange(a_start, a_end, a_range, "new" if b_range == timedelta(seconds=0) else "different")
    b_hash_range = HashRange(b_start, b_end, b_range, "new" if a_range == timedelta(seconds=0) else "different")
    return HashDifference(a_hash_range, b_hash_range, abs(b_range - a_range))


def get_differences_dict(hash_range: HashRange):
    return {
        "start_time": str(hash_range.start),
        "end_time": str(hash_range.end),
        "type": hash_range.type
    }


fps = 23.976216
output_dir = "out"
perceptual_match_threshold = 5 # when comparing perceptual hashes, anything below this hamming distance will be considered a match
extended_similarity_threshold = 12 # how many frames to ignore between matches, if they are similar to the matched frames
maximum_inter_match_search = 24 # how many frames to calculate hamming distance for in a batch


def main():
    db_path = "data/frame_hashes.db"

    label_a = "theatrical"
    table_a_name = "two_towers_theatrical"
    movie_a_filename = "C:\\Users\\obroo\\Lord of the Rings\\The Lord of the Rings The Two Towers (2002) Theatrical Remux-2160p HDR.mkv"

    label_b = "extended"
    table_b_name = "two_towers_extended"
    movie_b_filename = "C:\\Users\\obroo\\Lord of the Rings\\The Lord of the Rings The Two Towers (2002) Extended Remux-2160p HDR.mkv"

    print_json = False
    trim_videos = True
    grab_frames = True
    video_padding_seconds = 5

    matches = read_unique_valid_matches(db_path, table_a_name, table_b_name)

    table = []
    print()
    with Bar('Matching', max=len(matches)) as bar:
        for index in range(len(matches) - 1):
            matched = match(db_path, table_a_name, table_b_name, matches[index + 1], matches[index])
            if matched: table.append(matched)
            bar.next()

    def hash_difference_sort_key(difference: HashDifference) -> timedelta:
        return max(difference.a_range.range, difference.b_range.range)

    sorted_table = sorted(table, key=hash_difference_sort_key)

    tabulated = tabulate(
        [(
            x.a_range.start, x.a_range.end, x.a_range.type,
            x.b_range.start, x.b_range.end, x.b_range.type,
            x.a_range.range, x.b_range.range, x.range_difference
        ) for x in sorted_table],
        headers=["A Start", "A End", "A Type", "B Start", "B End", "B Type", "A Range", "B Range", "Range Difference"],
        tablefmt="github")

    print()
    print(f'Count ({len(sorted_table)}):')
    print()
    print(tabulated)

    if print_json:
        a_differences = [
            get_differences_dict(a_range)
            for a_range in [x.a_range for x in table]
            if a_range.range > timedelta(seconds=0)
        ]
        print(json.dumps(a_differences))

        b_differences = [
            get_differences_dict(b_range)
            for b_range in [x.b_range for x in table]
            if b_range.range > timedelta(seconds=0)
        ]
        print(json.dumps(b_differences))

    if trim_videos or grab_frames:
        print()
        with Bar('Cutting', max=len(sorted_table)) as bar:
            video_padding = timedelta(seconds=video_padding_seconds)
            for (index, row) in enumerate(sorted_table):

                a_start_time = row.a_range.start
                a_end_time = row.a_range.end
                a_range = row.a_range.range
                b_start_time = row.b_range.start
                b_end_time = row.b_range.end

                if trim_videos:
                    trim_video(movie_a_filename, label_a, index, a_start_time - video_padding, a_start_time)
                    trim_video(movie_a_filename, label_a, index, a_end_time - a_range, a_end_time + video_padding)
                    trim_video(movie_b_filename, label_b, index, b_start_time - video_padding, b_end_time + video_padding)

                if grab_frames:
                    grab_frame(movie_a_filename, label_a, index, a_start_time)
                    grab_frame(movie_b_filename, label_b, index, b_start_time)
                    grab_frame(movie_a_filename, label_a, index, a_end_time)
                    grab_frame(movie_b_filename, label_b, index, b_end_time)

                bar.next()


if __name__ == "__main__":
    main()
