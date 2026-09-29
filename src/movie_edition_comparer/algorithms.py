"""The two hashes a frame is given.

hash_md5 is of the pixels, and is equal only between frames that are the
same frame. hash_block_mean_0 is of the picture, and is equal -- or a few
bits apart -- between two renderings of one picture.
"""

import hashlib

import cv2
import numpy as np
from numpy import ndarray


def hash_md5(frame: ndarray) -> str:
    return hashlib.md5(frame.tobytes()).hexdigest()


def hash_block_mean_0(frame: ndarray) -> str:
    return serialize(cv2.img_hash.blockMeanHash(frame, mode=0))


def serialize(uint8_array: ndarray) -> str:
    return ''.join(format(x, '02x') for x in uint8_array.flatten())


def deserialize(hex_hash: str) -> ndarray:
    return np.array([int(hex_hash[i:i + 2], 16) for i in range(0, len(hex_hash), 2)], dtype=np.uint8)
