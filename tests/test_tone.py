"""One fixed curve takes PQ HDR pictures to SDR, the same for every film."""

import numpy as np

from movie_edition_comparer.tone import HDR_PEAK, HDR_TO_SDR, SDR_WHITE, nits_to_pq, pq_to_nits


def code(nits):
    return int(round(float(nits_to_pq(nits)) * 255))


def test_never_darkens_a_brighter_value():
    assert np.all(np.diff(HDR_TO_SDR.astype(int)) >= 0)


def test_keeps_black_black_and_takes_the_peak_to_white():
    assert HDR_TO_SDR[0] == 0
    assert HDR_TO_SDR[code(HDR_PEAK)] == 255


def test_leaves_the_darks_as_plain_pq_to_sdr_would():
    plain = np.round(np.clip(pq_to_nits(np.array(64 / 255)) / SDR_WHITE, 0, 1) ** (1 / 2.4) * 255)
    assert HDR_TO_SDR[64] == plain


def test_rolls_highlights_off_rather_than_clipping_them_at_sdr_white():
    assert HDR_TO_SDR[code(SDR_WHITE)] < 255
    assert HDR_TO_SDR[code(1000)] > HDR_TO_SDR[code(SDR_WHITE)]
