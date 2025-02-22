import hashlib

import cv2
import numpy as np

hashing_algorithms = {
    'md5': lambda img: get_frame_hash(img, 'md5'),
    'average': lambda img: serialize(cv2.img_hash.averageHash(img)),
    'perceptual': lambda img: serialize(cv2.img_hash.pHash(img)),
    'marr_hildreth': lambda img: serialize(cv2.img_hash.marrHildrethHash(img)),
    'radial_variance': lambda img: serialize(cv2.img_hash.radialVarianceHash(img)),
    'block_mean': lambda img: serialize(cv2.img_hash.blockMeanHash(img)),
}


def get_frame_hash(frame, hash_algorithm):
    hash_func = getattr(hashlib, hash_algorithm)()
    hash_func.update(frame.tobytes())
    return hash_func.hexdigest()


def serialize(uint8_array):
    return ''.join(format(x, '02x') for x in uint8_array.flatten())


def deserialize(hex_hash):
    return np.array([int(hex_hash[i:i + 2], 16) for i in range(0, len(hex_hash), 2)], dtype=np.uint8)


def get_column_name(algorithm):
    return f"hash_{algorithm}"
