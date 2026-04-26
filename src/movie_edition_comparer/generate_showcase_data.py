"""Generate data and images for the showcase website.

Runs the comparison pipeline for LOTR films and produces JSON data files
and web-optimized WebP images for a static site.

Usage:
    uv run python -m movie_edition_comparer.generate_showcase_data \
        --media-dir /mnt/data/Videos/Media \
        --output-dir showcase/public/data
"""

import argparse
import bisect
import json
import os
import re
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path

import cv2

from movie_edition_comparer.comparison import find_all_differences
from movie_edition_comparer.db import make_db_fetcher, read_chapters, read_unique_matches
from movie_edition_comparer.models import (
    ComparisonConfig,
    DifferenceType,
    FrameRange,
    SceneDifference,
)
from movie_edition_comparer.video import extract_frames


@dataclass(frozen=True)
class FilmConfig:
    slug: str
    title: str
    year: int
    db: str
    filename_pattern: str  # regex to match video filenames


FILM_CONFIGS = [
    FilmConfig(
        slug="fellowship",
        title="The Fellowship of the Ring",
        year=2001,
        db="data/fellowship.db",
        filename_pattern=r"Fellowship.*Ring.*\(2001\)",
    ),
    FilmConfig(
        slug="two_towers",
        title="The Two Towers",
        year=2002,
        db="data/two_towers.db",
        filename_pattern=r"Two Towers.*\(2002\)",
    ),
    FilmConfig(
        slug="return_of_the_king",
        title="The Return of the King",
        year=2003,
        db="data/return_of_the_king.db",
        filename_pattern=r"Return.*King.*\(2003\)",
    ),
]

MAX_SAMPLES = 6
SECONDS_PER_SAMPLE = 10


def discover_videos(media_dir: str) -> dict[str, dict[str, str]]:
    """Discover video files by matching filename patterns.

    Returns {film_slug: {"theatrical": path, "extended": path}}.
    """
    if not os.path.isdir(media_dir):
        return {}

    files = os.listdir(media_dir)
    result: dict[str, dict[str, str]] = {}

    for config in FILM_CONFIGS:
        editions = {}
        for f in files:
            if not re.search(config.filename_pattern, f):
                continue
            path = os.path.join(media_dir, f)
            if "Theatrical" in f:
                editions["theatrical"] = path
            elif "Extended" in f:
                editions["extended"] = path
        if editions:
            result[config.slug] = editions

    return result


def parse_chapter_time(time_str: str) -> float:
    """Parse 'HH:MM:SS.nnnnnnnnn' to seconds."""
    parts = time_str.split(":")
    h, m = int(parts[0]), int(parts[1])
    s = float(parts[2])
    return h * 3600 + m * 60 + s


def load_chapters(db_path: str, edition: str) -> list[dict]:
    """Load chapters from DB as list of {start_seconds, title}."""
    rows = read_chapters(db_path, edition)
    return [
        {"start_seconds": parse_chapter_time(start), "title": title}
        for start, title in rows
    ]


def find_chapter(frame: int, fps: float, chapters: list[dict]) -> str:
    """Return the chapter title active at the given frame."""
    if not chapters:
        return ""
    seconds = frame / fps
    starts = [ch["start_seconds"] for ch in chapters]
    idx = bisect.bisect_right(starts, seconds) - 1
    if idx < 0:
        return chapters[0]["title"]
    return chapters[idx]["title"]


def format_time(t: timedelta) -> str:
    """Format timestamp as HH:MM:SS."""
    total = int(t.total_seconds())
    h, remainder = divmod(total, 3600)
    m, s = divmod(remainder, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def sample_count(duration_seconds: float) -> int:
    """How many sample frames for a given duration."""
    if duration_seconds <= 0:
        return 0
    n = max(1, int(duration_seconds / SECONDS_PER_SAMPLE))
    return min(n, MAX_SAMPLES)


def sample_frames(frame_range: FrameRange, n: int) -> list[int]:
    """Return n evenly-spaced frame indices within the range (excluding endpoints)."""
    count = frame_range.frame_count
    if count <= 0 or n <= 0:
        return []
    if n == 1:
        return [frame_range.start + count // 2]
    step = count / (n + 1)
    return [frame_range.start + int(step * (i + 1)) for i in range(n)]


def collect_showcase_frames(
    differences: list[SceneDifference],
) -> tuple[list[int], list[int], dict[int, list[int]]]:
    """Collect frame indices needed for the showcase.

    Returns (a_frames, b_frames, samples_by_diff_index) where
    samples_by_diff_index maps difference index to sample frame indices
    for the edition with more content.
    """
    a_frames: list[int] = []
    b_frames: list[int] = []
    samples: dict[int, list[int]] = {}

    for i, diff in enumerate(differences):
        # First inner frame from each edition
        if diff.first_inner_a:
            a_frames.append(diff.first_inner_a.index)
        if diff.first_inner_b:
            b_frames.append(diff.first_inner_b.index)

        # Samples for longer differences
        a_dur = diff.a_range.inner_count / diff.fps
        b_dur = diff.b_range.inner_count / diff.fps

        a_samples = []
        b_samples = []

        if a_dur > SECONDS_PER_SAMPLE:
            n = sample_count(a_dur)
            a_samples = sample_frames(diff.a_range, n)
            a_frames.extend(a_samples)

        if b_dur > SECONDS_PER_SAMPLE:
            n = sample_count(b_dur)
            b_samples = sample_frames(diff.b_range, n)
            b_frames.extend(b_samples)

        if a_samples or b_samples:
            samples[i] = a_samples + b_samples

    return a_frames, b_frames, samples


def webp_path(edition: str, frame_index: int, thumb: bool = False) -> str:
    """Build relative image path for a frame."""
    suffix = "_thumb" if thumb else ""
    return f"images/{edition}/frame_{frame_index:012d}{suffix}.webp"


def _crop_letterbox(img):
    """Remove black letterbox bars from top and bottom."""
    import numpy as np
    row_means = img.mean(axis=(1, 2))
    top = 0
    for i, v in enumerate(row_means):
        if v > 10:
            top = i
            break
    bottom = img.shape[0]
    for i, v in enumerate(reversed(row_means)):
        if v > 10:
            bottom = img.shape[0] - i
            break
    if top > 0 or bottom < img.shape[0]:
        return img[top:bottom, :, :]
    return img


def convert_to_webp(
    png_path: str, output_path: str,
    width: int, quality: int,
):
    """Convert a PNG frame to WebP. Crops letterbox, resizes if width > 0. Skips if output exists."""
    if os.path.isfile(output_path):
        return

    img = cv2.imread(png_path)
    if img is None:
        return

    img = _crop_letterbox(img)
    if img.shape[0] == 0 or img.shape[1] == 0:
        return

    if width > 0:
        h, w = img.shape[:2]
        new_w = width
        new_h = max(1, int(h * (new_w / w)))
        img = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_AREA)

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    cv2.imwrite(output_path, img, [cv2.IMWRITE_WEBP_QUALITY, quality])


def build_difference_entry(
    diff: SceneDifference,
    index: int,
    chapters_a: list[dict],
    chapters_b: list[dict],
    a_sample_frames: list[int],
    b_sample_frames: list[int],
) -> dict:
    """Build a single difference JSON entry."""
    fps = diff.fps

    def edition_info(frame_range: FrameRange, chapters: list[dict]) -> dict:
        start_time = timedelta(seconds=frame_range.start / fps)
        end_time = timedelta(seconds=frame_range.end / fps)
        return {
            "start_frame": frame_range.start,
            "end_frame": frame_range.end,
            "start_time": format_time(start_time),
            "end_time": format_time(end_time),
            "duration_seconds": round(frame_range.inner_count / fps, 2),
            "chapter": find_chapter(frame_range.start, fps, chapters),
        }

    # Image frame indices
    a_images = []
    b_images = []
    if diff.first_inner_a:
        a_images.append(diff.first_inner_a.index)
    if diff.first_inner_b:
        b_images.append(diff.first_inner_b.index)
    a_images.extend(a_sample_frames)
    b_images.extend(b_sample_frames)

    # Reordered info
    reordered_info = None
    if diff.reordered_matches:
        b_indices = [m.b.index for m in diff.reordered_matches]
        min_time = format_time(timedelta(seconds=min(b_indices) / fps))
        max_time = format_time(timedelta(seconds=max(b_indices) / fps))
        reordered_info = {
            "time_range": f"{min_time}\u2013{max_time}",
            "matching_frames": len(diff.reordered_matches),
        }

    return {
        "index": index,
        "type": diff.difference_type,
        "theatrical": edition_info(diff.a_range, chapters_a),
        "extended": edition_info(diff.b_range, chapters_b),
        "duration_difference_seconds": round(diff.duration_difference.total_seconds(), 2),
        "images": {
            "theatrical": a_images,
            "extended": b_images,
        },
        "reordered_info": reordered_info,
    }


def process_film(
    config: FilmConfig,
    output_dir: str,
    cache_dir: str,
    videos: dict[str, str],
    full_width: int,
    thumb_width: int,
    quality: int,
    skip_frames: bool,
) -> dict:
    """Process a single film and write its data.json + images."""
    print(f"\n{'='*60}")
    print(f"  {config.title} ({config.year})")
    print(f"{'='*60}")

    film_dir = os.path.join(output_dir, config.slug)
    os.makedirs(film_dir, exist_ok=True)

    # Run comparison
    print("Reading matches...")
    matches = read_unique_matches(config.db, "theatrical", "extended")
    a_fetcher = make_db_fetcher(config.db, "theatrical")
    b_fetcher = make_db_fetcher(config.db, "extended")

    print("Finding differences...")
    comp_config = ComparisonConfig()
    differences = find_all_differences(matches, a_fetcher, b_fetcher, comp_config)
    differences.sort(key=lambda d: d.b_range.start)

    # Load chapters
    chapters_a = load_chapters(config.db, "theatrical")
    chapters_b = load_chapters(config.db, "extended")

    print(f"  {len(differences)} differences found")

    # Collect needed frames
    a_frames, b_frames, samples_by_diff = collect_showcase_frames(differences)

    # Extract and convert frames
    if not skip_frames and videos:
        raw_dir = os.path.join(cache_dir, config.slug)

        if "theatrical" in videos:
            a_raw = os.path.join(raw_dir, "theatrical")
            print("Extracting theatrical frames...")
            extract_frames(
                videos["theatrical"], a_frames, a_raw,
                db_path=config.db, edition="theatrical",
            )

        if "extended" in videos:
            b_raw = os.path.join(raw_dir, "extended")
            print("Extracting extended frames...")
            extract_frames(
                videos["extended"], b_frames, b_raw,
                db_path=config.db, edition="extended",
            )

        # Convert to WebP
        print("Converting to WebP...")
        for edition, frame_list in [("theatrical", a_frames), ("extended", b_frames)]:
            raw_edition_dir = os.path.join(raw_dir, edition)
            for idx in sorted(set(frame_list)):
                png = os.path.join(raw_edition_dir, f"frame_{idx:012d}.png")
                if not os.path.isfile(png):
                    continue
                full_out = os.path.join(film_dir, webp_path(edition, idx))
                thumb_out = os.path.join(film_dir, webp_path(edition, idx, thumb=True))
                convert_to_webp(png, full_out, full_width, quality)
                convert_to_webp(png, thumb_out, thumb_width, quality)

    # Build JSON
    diff_entries = []
    for i, diff in enumerate(differences):
        a_samples = []
        b_samples = []
        if i in samples_by_diff:
            all_samples = samples_by_diff[i]
            # Split back into a/b based on frame ranges
            for s in all_samples:
                if diff.a_range.start <= s <= diff.a_range.end:
                    a_samples.append(s)
                else:
                    b_samples.append(s)

        diff_entries.append(build_difference_entry(
            diff, i + 1, chapters_a, chapters_b, a_samples, b_samples,
        ))

    # Frame counts
    import sqlite3
    from contextlib import closing
    with closing(sqlite3.connect(config.db)) as conn:
        t_count = conn.execute(
            "SELECT COUNT(*) FROM frame_hashes WHERE edition = 'theatrical'"
        ).fetchone()[0]
        e_count = conn.execute(
            "SELECT COUNT(*) FROM frame_hashes WHERE edition = 'extended'"
        ).fetchone()[0]

    data = {
        "film": {
            "slug": config.slug,
            "title": config.title,
            "year": config.year,
            "fps": comp_config.fps,
            "theatrical_frames": t_count,
            "extended_frames": e_count,
        },
        "chapters": {
            "theatrical": chapters_a,
            "extended": chapters_b,
        },
        "differences": diff_entries,
    }

    data_path = os.path.join(film_dir, "data.json")
    with open(data_path, "w") as f:
        json.dump(data, f, indent=2)
    print(f"Wrote {data_path}")

    # Find the best hero frame (longest unique_to_b with images)
    hero_frame = None
    hero_duration = 0
    for entry in diff_entries:
        if entry["type"] == "unique_to_b" and entry["images"]["extended"]:
            if entry["extended"]["duration_seconds"] > hero_duration:
                hero_duration = entry["extended"]["duration_seconds"]
                hero_frame = entry["images"]["extended"][0]

    # Compute stats
    stats = {
        "added": sum(1 for d in differences if d.difference_type == DifferenceType.UNIQUE_TO_B),
        "removed": sum(1 for d in differences if d.difference_type == DifferenceType.UNIQUE_TO_A),
        "modified": sum(1 for d in differences if d.difference_type == DifferenceType.MODIFIED),
        "reordered": sum(1 for d in differences if d.difference_type == DifferenceType.REORDERED),
        "extra_minutes": round(sum(
            d.duration_difference.total_seconds() for d in differences
        ) / 60),
    }

    return {
        "slug": config.slug,
        "title": config.title,
        "year": config.year,
        "total_differences": len(differences),
        "theatrical_frames": t_count,
        "extended_frames": e_count,
        "hero_frame": hero_frame,
        "stats": stats,
    }


def main():
    parser = argparse.ArgumentParser(description="Generate showcase website data")
    parser.add_argument("--output-dir", default="showcase/public/data",
                        help="Output directory for data and images")
    parser.add_argument("--media-dir", default=None,
                        help="Directory containing video files (auto-discovered)")
    parser.add_argument("--film", default=None,
                        help="Process only a specific film slug")
    parser.add_argument("--skip-frames", action="store_true",
                        help="Skip frame extraction and WebP conversion")
    parser.add_argument("--quality", type=int, default=90,
                        help="WebP quality 1-100 (default: 90)")
    parser.add_argument("--full-width", type=int, default=0,
                        help="Full-size image width, 0 for original (default: 0)")
    parser.add_argument("--thumb-width", type=int, default=480,
                        help="Thumbnail width (default: 480)")
    parser.add_argument("--cache-dir", default="showcase/.cache",
                        help="Directory for raw PNG frames (default: showcase/.cache)")
    args = parser.parse_args()

    videos = discover_videos(args.media_dir) if args.media_dir else {}

    configs = FILM_CONFIGS
    if args.film:
        configs = [c for c in configs if c.slug == args.film]
        if not configs:
            print(f"Unknown film: {args.film}")
            return

    os.makedirs(args.output_dir, exist_ok=True)
    film_summaries = []

    for config in configs:
        film_videos = videos.get(config.slug, {})
        if not film_videos and not args.skip_frames:
            print(f"Skipping {config.title}: no video files found")
            if not args.media_dir:
                print("  (use --media-dir to specify video location)")

        summary = process_film(
            config, args.output_dir, args.cache_dir, film_videos,
            args.full_width, args.thumb_width, args.quality,
            args.skip_frames,
        )
        film_summaries.append(summary)

    # Write manifest — merge with existing if only processing a subset of films
    manifest_path = os.path.join(args.output_dir, "manifest.json")
    existing_films: dict[str, dict] = {}
    if os.path.isfile(manifest_path):
        with open(manifest_path) as f:
            existing = json.load(f)
        for film in existing.get("films", []):
            existing_films[film["slug"]] = film

    for summary in film_summaries:
        existing_films[summary["slug"]] = summary

    # Order by year
    all_films = sorted(existing_films.values(), key=lambda f: f["year"])
    manifest = {
        "films": all_films,
    }
    manifest_path = os.path.join(args.output_dir, "manifest.json")
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)
    print(f"\nWrote {manifest_path}")


if __name__ == "__main__":
    main()
