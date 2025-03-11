import hashlib
from enum import Enum

import cv2
import numpy as np
from numpy import ndarray


class HashAlgorithm(Enum):
    MD5 = 1
    AVERAGE = 2
    PERCEPTUAL = 3
    MARR_HILDRETH = 4
    RADIAL_VARIANCE = 5
    BLOCK_MEAN_0 = 6


hashing_algorithms = {
    HashAlgorithm.MD5: lambda img: get_frame_hash(img, 'md5'),
    HashAlgorithm.AVERAGE: lambda img: serialize(cv2.img_hash.averageHash(img)),
    HashAlgorithm.PERCEPTUAL: lambda img: serialize(cv2.img_hash.pHash(img)),
    HashAlgorithm.MARR_HILDRETH: lambda img: serialize(cv2.img_hash.marrHildrethHash(img)),
    HashAlgorithm.RADIAL_VARIANCE: lambda img: serialize(cv2.img_hash.radialVarianceHash(img)),
    HashAlgorithm.BLOCK_MEAN_0: lambda img: serialize(cv2.img_hash.blockMeanHash(img, mode=0)),
}


def get_frame_hash(frame: ndarray, hash_algorithm: str) -> str:
    hash_func = getattr(hashlib, hash_algorithm)()
    hash_func.update(frame.tobytes())
    return hash_func.hexdigest()


def serialize(uint8_array: ndarray) -> str:
    return ''.join(format(x, '02x') for x in uint8_array.flatten())


def deserialize(hex_hash: str) -> ndarray:
    return np.array([int(hex_hash[i:i + 2], 16) for i in range(0, len(hex_hash), 2)], dtype=np.uint8)


def get_column_name(algorithm: HashAlgorithm) -> str:
    return f"hash_{algorithm.name.lower()}"
