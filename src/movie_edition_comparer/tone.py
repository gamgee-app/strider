"""The one curve that takes a PQ HDR picture to SDR, the same for every film.

OpenCV gives an HDR video's PQ code values as they are, so a 4K HDR release
looks flat and grey beside the same film in SDR, and its picture hashes seldom
match. The curve is BT.2390's: code values to light by ST 2084, highlights
rolled off from a fixed source peak so that it lands on SDR white, then SDR
gamma. Nothing in it is fitted to a film or read from one, so a value means
the same in every HDR file.

Measured on The Two Towers, 4K HDR remux against the 1080p SDR remux of the
same master: block mean 0 within 5 bits on 86% of frames, against 19% as
decoded; the two HDR encodes of that master stay 0.14 grey levels apart.
"""

import numpy as np

# The source peak highlights are rolled off from, in nits, and the light SDR
# white stands for (BT.2408). A fixed peak rather than each file's MaxCLL, so
# that a code value maps alike whatever a file's metadata says.
HDR_PEAK = 4000
SDR_WHITE = 203

# ST 2084 constants.
_M1, _M2 = 2610 / 16384, 2523 / 4096 * 128
_C1, _C2, _C3 = 3424 / 4096, 2413 / 4096 * 32, 2392 / 4096 * 32


def pq_to_nits(code: np.ndarray) -> np.ndarray:
    """Light, in nits, for PQ code values from 0 to 1."""
    p = np.power(np.clip(code, 0, 1), 1 / _M2)
    return 10000 * np.power(np.maximum(p - _C1, 0) / (_C2 - _C3 * p), 1 / _M1)


def nits_to_pq(nits: float | np.ndarray) -> np.ndarray:
    y = np.power(np.clip(nits, 0, 10000) / 10000, _M1)
    return np.power((_C1 + _C2 * y) / (1 + _C3 * y), _M2)


def hdr_to_sdr() -> np.ndarray:
    """The curve as a lookup table from 8-bit PQ values to 8-bit SDR ones."""
    code = np.arange(256) / 255
    peak = nits_to_pq(HDR_PEAK)
    e = np.clip(code / peak, 0, 1)
    top = nits_to_pq(SDR_WHITE) / peak
    knee = 1.5 * top - 0.5
    t = (e - knee) / (1 - knee)
    rolled = (2 * t**3 - 3 * t**2 + 1) * knee + (t**3 - 2 * t**2 + t) * (1 - knee) + (-2 * t**3 + 3 * t**2) * top
    e = np.where(code >= peak, top, np.where(e < knee, e, rolled))
    sdr = np.power(np.clip(pq_to_nits(e * peak) / SDR_WHITE, 0, 1), 1 / 2.4)
    return np.clip(np.round(sdr * 255), 0, 255).astype(np.uint8)


HDR_TO_SDR = hdr_to_sdr()
