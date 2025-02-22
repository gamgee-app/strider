import datetime
import sqlite3

import cv2

from .algorithms import deserialize


def read_hashes():
    conn = sqlite3.connect("data/frame_hashes.db")
    cursor = conn.cursor()

    cursor.execute("""
        SELECT 
            frame_index,
            md5_hash, 
            average_hash, 
            perceptual_hash, 
            marr_hildreth_hash, 
            radial_variance_hash, 
            block_mean_hash
        FROM
            two_towers_theatrical
    """)
    theatrical = cursor.fetchall()

    cursor.execute("""
        SELECT 
            frame_index,
            md5_hash, 
            average_hash, 
            perceptual_hash, 
            marr_hildreth_hash, 
            radial_variance_hash, 
            block_mean_hash
        FROM
            two_towers_extended
    """)
    extended = cursor.fetchall()

    conn.close()

    return theatrical, extended


def frame_to_time(frame):
    return str(datetime.timedelta(seconds=frame / 24))


def compare_hash_arrays(theatricals, extendeds):
    differences = []
    i = 0
    j = 0
    while i < len(theatricals) and j < len(extendeds):
        theatrical = theatricals[i]
        extended = extendeds[j]
        (a_index, a_md5, a_average, a_perceptual, a_marr_hildreth, a_radial_variance, a_block_mean) = theatrical
        (b_index, b_md5, b_average, b_perceptual, b_marr_hildreth, b_radial_variance, b_block_mean) = extended

        if a_index != i or b_index != j:
            raise Exception("Missing frames")

        if compare_hashes(theatrical, extended) != HashEquality.DIFFERENT:
            i += 1
            j += 1
        else:
            print("Finding difference")
            difference = find_difference(theatricals, i, extendeds, j)

            if difference is None:
                raise Exception(f"Different at theatrical {a_index} ({frame_to_time(a_index)}) "
                                f"and extended {b_index} ({frame_to_time(b_index)})")

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


def compare_hashes(theatrical, extended, should_print=True):
    (a_index, a_md5, a_average, a_perceptual, a_marr_hildreth, a_radial_variance, a_block_mean) = theatrical
    (b_index, b_md5, b_average, b_perceptual, b_marr_hildreth, b_radial_variance, b_block_mean) = extended

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


def find_difference(theatricals, i, extendeds, j):
    next_5_theatrical = theatricals[i:i + (24 * 60 * 5)]
    next_5_extended = extendeds[j:j + (24 * 60 * 5)]

    for maybe_theatrical in next_5_theatrical:
        maybe_theatrical_frame = maybe_theatrical[0]
        print(f"{maybe_theatrical_frame} theatrical ({frame_to_time(maybe_theatrical_frame)})")
        for maybe_extended in next_5_extended:
            maybe_extended_frame = maybe_extended[0]
            compared = compare_hashes(maybe_theatrical, maybe_extended, False)
            if compared in (HashEquality.EQUAL, HashEquality.EQUIVALENT):
                print(
                    f"Got theatrical {maybe_theatrical_frame} ({frame_to_time(maybe_theatrical_frame)}) and extended {maybe_extended_frame} ({frame_to_time(maybe_extended_frame)})")
                return maybe_theatrical_frame, maybe_extended_frame


def main():
    (theatrical, extended) = read_hashes()
    compare_hash_arrays(theatrical, extended)


if __name__ == "__main__":
    main()
