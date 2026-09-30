"""The hashes a frame is given.

hash_md5 is of the pixels, and is equal only between frames that are the
same frame. The rest are of the picture, and are equal -- or a few bits
apart -- between two renderings of one picture. block_mean_0 is the one the
comparison goes by unless told otherwise; the others are kept so that they
can be measured against it on real films.
"""

import hashlib

import cv2
import numpy as np
from numpy import ndarray


def hash_md5(frame: ndarray) -> str:
    return hashlib.md5(frame.tobytes()).hexdigest()


def hash_block_mean_0(frame: ndarray) -> str:
    return serialize(cv2.img_hash.blockMeanHash(frame, mode=0))


PICTURE_HASHES = {
    "block_mean_0": hash_block_mean_0,                                        # 256 bits
    "block_mean_1": lambda frame: serialize(cv2.img_hash.blockMeanHash(frame, mode=1)),  # 968
    "average": lambda frame: serialize(cv2.img_hash.averageHash(frame)),      # 64
    "phash": lambda frame: serialize(cv2.img_hash.pHash(frame)),              # 64
    "marr_hildreth": lambda frame: serialize(cv2.img_hash.marrHildrethHash(frame)),  # 576
    "radial_variance": lambda frame: serialize(cv2.img_hash.radialVarianceHash(frame)),  # 320
}


def serialize(uint8_array: ndarray) -> str:
    return ''.join(format(x, '02x') for x in uint8_array.flatten())


def deserialize(hex_hash: str) -> ndarray:
    return np.array([int(hex_hash[i:i + 2], 16) for i in range(0, len(hex_hash), 2)], dtype=np.uint8)
