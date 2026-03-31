"""Generate alignment verification data for suspicious boundaries.

Produces alignment_data.json which is loaded by alignment.html for
visual boundary confirmation. Extracts frames needed for the viewer.

Usage:
    uv run python -m movie_edition_comparer.generate_alignment_data \
        --db data/frame_hashes_migrated.db \
        --edition-a two_towers_theatrical \
        --edition-b two_towers_extended \
        --movie-a theatrical.mkv \
        --movie-b extended.mkv
"""

import argparse
import json

from movie_edition_comparer.comparison import find_all_differences, hamming_distance
from movie_edition_comparer.db import make_db_fetcher, read_hashes_from_db, read_unique_matches
from movie_edition_comparer.models import ComparisonConfig
from movie_edition_comparer.video import extract_frames

NUM_PAIRS = 11
CENTER_PAIR = 5
OFFSET_RANGE = range(-5, 6)
MAX_MIN_HD = 0


def find_suspicious_boundaries(differences):
    """Return indices of differences where min boundary hamming distance <= MAX_MIN_HD."""
    suspicious = []
    for i, d in enumerate(differences):
        sm = d.start_match
        em = d.end_match
        fia = d.first_inner_a
        fib = d.first_inner_b
        lia = d.last_inner_a
        lib = d.last_inner_b

        before_cross = hamming_distance(sm.a.hash, sm.b.hash) if sm else None
        after_cross = hamming_distance(em.a.hash, em.b.hash) if em else None
        before_adj_a = hamming_distance(sm.a.hash, fia.hash) if sm and fia else None
        before_adj_b = hamming_distance(sm.b.hash, fib.hash) if sm and fib else None
        last_adj_a = hamming_distance(lia.hash, em.a.hash) if lia and em else None
        last_adj_b = hamming_distance(lib.hash, em.b.hash) if lib and em else None

        boundary_diffs = []
        if before_cross is not None and before_adj_a is not None:
            boundary_diffs.append(abs(before_adj_a - before_cross))
        if before_cross is not None and before_adj_b is not None:
            boundary_diffs.append(abs(before_adj_b - before_cross))
        if after_cross is not None and last_adj_a is not None:
            boundary_diffs.append(abs(last_adj_a - after_cross))
        if after_cross is not None and last_adj_b is not None:
            boundary_diffs.append(abs(last_adj_b - after_cross))
        min_hd = min(boundary_diffs) if boundary_diffs else -1

        if min_hd <= MAX_MIN_HD:
            suspicious.append(i)

    return suspicious


def generate_cases(differences, suspicious_indices, db_path, edition_a, edition_b):
    """Build alignment case data for each suspicious boundary."""
    cases = []
    t_frames = set()
    e_frames = set()

    for i in suspicious_indices:
        d = differences[i]
        sm = d.start_match
        em = d.end_match

        for boundary_type, t_base, e_base in [
            ("start", sm.a.index, sm.b.index),
            ("end", em.a.index, em.b.index),
        ]:
            t_hashes = {
                h.index: h.hash
                for h in read_hashes_from_db(db_path, edition_a, t_base - 10, t_base + 11)
            }
            e_hashes = {
                h.index: h.hash
                for h in read_hashes_from_db(db_path, edition_b, e_base - 10, e_base + 11)
            }

            offsets = {}
            for offset in OFFSET_RANGE:
                t_anchor = t_base + offset
                dists = []
                for pair_i in range(NUM_PAIRS):
                    ti = t_anchor + (pair_i - CENTER_PAIR)
                    ei = e_base + (pair_i - CENTER_PAIR)
                    th = t_hashes.get(ti)
                    eh = e_hashes.get(ei)
                    if th and eh:
                        dists.append(hamming_distance(th, eh))
                    else:
                        dists.append(-1)
                    t_frames.add(ti)
                    e_frames.add(ei)

                offsets[str(offset)] = {"tAnchor": t_anchor, "dists": dists}

            cases.append({
                "diffNum": i + 1,
                "boundary": boundary_type,
                "tBoundary": t_base,
                "eBoundary": e_base,
                "tOther": em.a.index if boundary_type == "start" else sm.a.index,
                "eOther": em.b.index if boundary_type == "start" else sm.b.index,
                "type": d.difference_type,
                "offsets": offsets,
            })

    cases.sort(key=lambda c: c["tBoundary"])
    return cases, sorted(t_frames), sorted(e_frames)


def main():
    parser = argparse.ArgumentParser(description="Generate alignment verification data")
    parser.add_argument("--db", required=True, help="Path to database file")
    parser.add_argument("--edition-a", required=True)
    parser.add_argument("--edition-b", required=True)
    parser.add_argument("--movie-a", default=None, help="Path to edition A video (for frame extraction)")
    parser.add_argument("--movie-b", default=None, help="Path to edition B video (for frame extraction)")
    parser.add_argument("--output", default="alignment_data.json")
    parser.add_argument("--frames-dir", default="frames")
    parser.add_argument("--label-a", default="theatrical")
    parser.add_argument("--label-b", default="extended")
    args = parser.parse_args()

    config = ComparisonConfig()

    print("Reading unique matches...")
    matches = read_unique_matches(args.db, args.edition_a, args.edition_b)
    a_fetcher = make_db_fetcher(args.db, args.edition_a)
    b_fetcher = make_db_fetcher(args.db, args.edition_b)

    print("Finding differences...")
    differences = find_all_differences(matches, a_fetcher, b_fetcher, config)
    differences.sort(key=lambda d: max(d.a_range.inner_count, d.b_range.inner_count))

    print("Identifying suspicious boundaries...")
    suspicious = find_suspicious_boundaries(differences)
    print(f"  {len(suspicious)} differences with min boundary HD <= {MAX_MIN_HD}")

    print("Generating alignment data...")
    cases, t_frames, e_frames = generate_cases(
        differences, suspicious, args.db, args.edition_a, args.edition_b,
    )
    print(f"  {len(cases)} cases, {len(t_frames)} theatrical frames, {len(e_frames)} extended frames")

    with open(args.output, "w") as f:
        json.dump(cases, f, indent=2)
    print(f"Wrote {args.output}")

    if args.movie_a and args.movie_b:
        import os

        a_dir = os.path.join(args.frames_dir, args.label_a)
        b_dir = os.path.join(args.frames_dir, args.label_b)

        print(f"Extracting {args.label_a} frames...")
        extract_frames(args.movie_a, t_frames, a_dir,
                       db_path=args.db, edition=args.edition_a)
        print(f"Extracting {args.label_b} frames...")
        extract_frames(args.movie_b, e_frames, b_dir,
                       db_path=args.db, edition=args.edition_b)


if __name__ == "__main__":
    main()
