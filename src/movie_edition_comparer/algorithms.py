import hashlib

import cv2
import numpy as np
from numpy import ndarray

HASH_COLUMN = "hash"


def hash_frame(img: ndarray) -> str:
    """Compute the block mean hash (mode 0) for a video frame."""
    return serialize(cv2.img_hash.blockMeanHash(img, mode=0))


def hash_frame_md5(img: ndarray) -> str:
    """Compute MD5 hash of raw pixel data."""
    return hashlib.md5(img.tobytes()).hexdigest()


def serialize(uint8_array: ndarray) -> str:
    return ''.join(format(x, '02x') for x in uint8_array.flatten())


def deserialize(hex_hash: str) -> ndarray:
    return np.array([int(hex_hash[i:i + 2], 16) for i in range(0, len(hex_hash), 2)], dtype=np.uint8)
