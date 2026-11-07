# Comparing editions whatever the master

A summary of the work on the `master-invariant-compare` branch (October–November 2026).

## The aim

Compare two releases of a film so that the master they were made from does not matter:

- the same edition from a different master should show almost no differences in where frames sit;
- results between different editions should be alike whichever masters are compared;
- only the stored picture hashes and block averages are used, with no new features read from the films.

## Position is not picture

A link between two frames says they are at the same point in the film, carrying the same footage. It does
not say they look the same. A remaster that recolours a scene (Arwen's vision, for one) is a real
difference, and is reported as one. Alignment (which frame corresponds to which) is kept apart from how
different the linked frames look.

## How frames are placed

1. **Hashes** line the releases up where the pictures hash alike.
2. **Structure check.** Each frame's inner 14×14 block averages and their gradients, each z-scored within
   the frame, so that brightness, contrast and grade drop out. Two frames are the same footage when their
   structures are within `SAME_STRUCTURE` (0.35). Links are moved up to two frames, unlinked when too far
   apart, and grown along runs that agree.
3. **Fill**, up to four rounds:
   - follow diagonals from sure links (distinct, with equal frame gaps on both sides);
   - follow the dominant offset within 240 frames, where it holds at least half the links;
   - fill short gaps (up to 24 frames) between links;
   - inside the fill, a frame may be placed at up to 1.6× the usual limit, since the footage around it
     puts it there.
4. **Flat frames** (black and other flat pictures, standard deviation under 2) cannot be told from one
   another, so two flat frames are 0 apart. Runs of repeated flat frames are split into single frames so
   that black lines up with black, and a flat stretch is unlinked when it is not held between shared
   footage within 24 frames.

## How linked frames look: regraded

For each pair of releases, one tone curve over the whole film maps each grey level of one to the level the
other uses for it (the median per level, kept monotone). That absorbs one release being darker overall, or
an HDR release taken to SDR. What is left after the curve, averaged over about a second (±12 links), is how
far apart the frames look. Footage in the same place that is more than 6 grey levels apart is reported as
`regraded`; two encodes of one master sit near 0.6. Each reported row carries the value (`grey_apart`).

The kinds reported are added, removed, replaced (not the same footage), moved, reencoded (same footage,
same place, looking alike) and regraded.

## Results

Same edition, share of frames reported added, removed, replaced or moved (median):

| Releases compared | Hashes alone | Now |
|---|---|---|
| Same master | — | 0.2% |
| Same master, HDR vs SDR | — | 0.5% |
| Different masters | 53.1% | 0.7% |

Share of the film reported regraded (median):

| Releases compared | Regraded |
|---|---|
| Same master, both SDR or both HDR | 0.0% (at most 0.3%) |
| Same master, HDR vs SDR | 26% |
| Different masters | about 66% |

- Between the masters the film-wide tone curve is near identity: the remaster's changes are shot by shot.
  The largest is Arwen's vision, 54 grey levels apart over 1,211 frames from 1:40:22.
- The 26% for HDR vs SDR mixes the 4K and 1080p discs' own grades with error in the fixed HDR-to-SDR
  curve; this data cannot tell the two apart.

## Facts checked along the way

- The theatrical and extended end credits never match (other font sizes, and the extended has the fan club
  credits), so any link between them is false.
- The Two Towers extended remaster remux and hybrid (both FraMeSToR) carry 120 frames of black at 1:46:34
  (frames 153,307–153,426), the disc break, checked by eye. The 4K, BHD and HONE releases leave it out.
- The AMZN releases lack the first 48 frames of the disc releases.

## Still open

- The overnight analysis script gets the AMZN start offset backwards (and probably HONE's), which
  understates AMZN's agreement between editions in the earlier report.
- Not checked by eye: that logos and file endings differ genuinely, the 5 end-logo frames reported moved
  in the remaster vs VC-1 credits, and a 12-frame dissolve linked falsely at 1:21:30.
- Flat frames include white, so a white flash could be linked to black.
- Proposed, not approved: an edge-map feature, and scaling the structure check for comparing by averages
  alone.
- The Ithilien still is still reported as replaced.

## Where things are

- Code: `compare_hashes.py` (placing, regraded), `averages.py` (structure), `compare_averages.py`.
- Tests: `tests/test_check_by_averages.py`, `tests/test_regraded.py`.
- The databases are not in git; the structure and regrade are worked out from the stored block averages,
  so existing databases need no new hashing.
- A page showing the process: https://claude.ai/artifact/Uco1NzctXSsTxftFVfHyNV
