import datetime
import sqlite3

import cv2

from algorithms import deserialize, hashing_algorithms, get_column_name


def read_hashes(db_path: str, table_a_name: str, table_b_name: str):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    column_names = [get_column_name(x) for x in hashing_algorithms]

    cursor.execute(f"""
        SELECT 
            frame_index,
            {",".join(column_names)}
        FROM
            {table_a_name}
    """)
    hashes_a = cursor.fetchall()

    cursor.execute(f"""
        SELECT 
            frame_index,
            {",".join(column_names)}
        FROM
            {table_b_name}
    """)
    hashes_b = cursor.fetchall()

    conn.close()

    return hashes_a, hashes_b


def frame_to_time(frame):
    return str(datetime.timedelta(seconds=frame / 24))


def compare_hash_arrays(hash_array_a, hash_array_b):
    differences = []
    i = 0
    j = 0
    while i < len(hash_array_a) and j < len(hash_array_b):
        hashes_a = hash_array_a[i]
        a_index = hashes_a[0]

        hashes_b = hash_array_b[j]
        b_index = hashes_b[0]

        if a_index != i or b_index != j:
            raise Exception("Missing frames")

        if compare_hashes(hashes_a, hashes_b) != HashEquality.DIFFERENT:
            i += 1
            j += 1
        else:
            print("Finding difference")
            difference = find_difference(hash_array_a, i, hash_array_b, j)

            if difference is None:
                raise Exception(f"Different at A {a_index} ({frame_to_time(a_index)}) "
                                f"and B {b_index} ({frame_to_time(b_index)})")

            (equivalent_a_index, equivalent_b_index) = difference
            differences.append(
                (frame_to_time(a_index),
                 frame_to_time(equivalent_a_index),
                 frame_to_time(b_index),
                 frame_to_time(equivalent_b_index))
            )
            (i, j) = (equivalent_a_index + 1, equivalent_b_index + 1)
            print(f"Found difference: {i} ({frame_to_time(i)}) to {j} ({frame_to_time(j)})")

    for difference in differences:
        print(difference)


from enum import Enum


class HashEquality(Enum):
    EQUAL = 1
    EQUIVALENT = 2
    SIMILAR = 3
    DIFFERENT = 4


def compare_hashes(hashes_a, hashes_b, should_print=True):
    (a_index, a_md5, a_average, a_perceptual, a_marr_hildreth, a_radial_variance, a_block_mean) = hashes_a
    (b_index, b_md5, b_average, b_perceptual, b_marr_hildreth, b_radial_variance, b_block_mean) = hashes_b

    if a_md5 == b_md5:
        if should_print: print(
            f"{a_index} frame ({frame_to_time(a_index)}) is equal to {b_index} frame ({frame_to_time(b_index)})")
        return HashEquality.EQUAL
    elif (a_average == b_average
          or a_perceptual == b_perceptual
          or a_marr_hildreth == b_marr_hildreth
          or a_radial_variance == b_radial_variance
          or a_block_mean == b_block_mean):
        if should_print: print(
            f"{a_index} frame ({frame_to_time(a_index)}) is equivalent to {b_index} frame ({frame_to_time(b_index)})")
        return HashEquality.EQUIVALENT
    else:
        compared_average = cv2.norm(deserialize(a_average), deserialize(b_average), cv2.NORM_HAMMING)
        compared_perceptual = cv2.norm(deserialize(a_perceptual), deserialize(b_perceptual), cv2.NORM_HAMMING)
        compared_marr_hildreth = cv2.norm(deserialize(a_marr_hildreth), deserialize(b_marr_hildreth), cv2.NORM_HAMMING)
        # compared_radial_variance is more complicated than simply norm_hamming
        compared_block_mean = cv2.norm(deserialize(a_block_mean), deserialize(b_block_mean), cv2.NORM_HAMMING)
        if min(compared_average, compared_perceptual, compared_marr_hildreth, compared_block_mean) <= 1:
            if should_print: print(
                f"{a_index} frame ({frame_to_time(a_index)}) is similar to {b_index} frame ({frame_to_time(b_index)})")
            return HashEquality.SIMILAR
        else:
            if should_print: print(
                f"{a_index} frame ({frame_to_time(a_index)}) is different to {b_index} frame ({frame_to_time(b_index)})")

    return HashEquality.DIFFERENT


def find_difference(hash_array_a, i, hash_array_b, j):
    next_5_hashes_a = hash_array_a[i:i + (24 * 60 * 5)]
    next_5_hashes_b = hash_array_b[j:j + (24 * 60 * 5)]

    for maybe_a_hashes in next_5_hashes_a:
        maybe_a_hash = maybe_a_hashes[0]
        print(f"{maybe_a_hash} A ({frame_to_time(maybe_a_hash)})")
        for maybe_b_hashes in next_5_hashes_b:
            maybe_b_hash = maybe_b_hashes[0]
            compared = compare_hashes(maybe_a_hashes, maybe_b_hashes, False)
            if compared in (HashEquality.EQUAL, HashEquality.EQUIVALENT):
                print(
                    f"Got A {maybe_a_hash} ({frame_to_time(maybe_a_hash)}) and B {maybe_b_hash} ({frame_to_time(maybe_b_hash)})")
                return maybe_a_hash, maybe_b_hash


def main():
    (hashes_a, hashes_b) = read_hashes("data/frame_hashes.db", "two_towers_theatrical", "two_towers_extended")
    compare_hash_arrays(hashes_a, hashes_b)


if __name__ == "__main__":
    main()
