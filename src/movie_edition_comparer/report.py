"""Generate an HTML visual verification report for scene differences."""

import os
from datetime import timedelta

from movie_edition_comparer.comparison import hamming_distance
from movie_edition_comparer.models import DifferenceType, FrameRange, SceneDifference
from movie_edition_comparer.video import _clip_filename, _frame_filename, extract_clips, extract_frames


def _ts(t: timedelta) -> str:
    """Format a timestamp as HH:MM:SS."""
    total = int(t.total_seconds())
    h, remainder = divmod(total, 3600)
    m, s = divmod(remainder, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def _dur(frames: int, fps: float) -> str:
    """Format a duration as human-readable text with frame count."""
    seconds = frames / fps
    if seconds < 60:
        return f"{seconds:.1f} seconds ({frames} frames)"
    minutes = seconds / 60
    return f"{minutes:.1f} minutes ({frames} frames)"


def _sample_frames(frame_range: FrameRange, n: int) -> list[int]:
    """Return n evenly-spaced frame indices within the range (excluding endpoints)."""
    count = frame_range.frame_count
    if count <= 0 or n <= 0:
        return []
    if n == 1:
        return [frame_range.start + count // 2]
    step = count / (n + 1)
    return [frame_range.start + int(step * (i + 1)) for i in range(n)]


def _type_class(difference_type: str) -> str:
    return {
        DifferenceType.UNIQUE_TO_B: "type-added",
        DifferenceType.UNIQUE_TO_A: "type-removed",
        DifferenceType.MODIFIED: "type-modified",
        DifferenceType.REORDERED: "type-reordered",
    }.get(difference_type, "")


def _type_label(difference_type: str) -> str:
    return {
        DifferenceType.UNIQUE_TO_B: "Added in B",
        DifferenceType.UNIQUE_TO_A: "Only in A",
        DifferenceType.MODIFIED: "Modified",
        DifferenceType.REORDERED: "Reordered",
    }.get(difference_type, difference_type)


def _img_tag(frames_dir: str, frame_index: int) -> str:
    """Return an <img> tag referencing a frame file, relative to the report."""
    path = os.path.join(frames_dir, _frame_filename(max(frame_index, 0)))
    return f'<img loading="lazy" src="{path}">'


def _diff_filename(idx_a: int, idx_b: int) -> str:
    return f"diff_{max(idx_a, 0):012d}_{max(idx_b, 0):012d}.png"


def _read_frame_at(cap, frame_index: int):
    """Seek and read a single frame from an open VideoCapture."""
    import cv2
    cap.set(cv2.CAP_PROP_POS_FRAMES, max(frame_index, 0))
    ret, frame = cap.read()
    return frame if ret else None


def _generate_diff_images(
    differences: list[SceneDifference],
    movie_a: str, movie_b: str,
    diff_dir: str,
):
    """Generate difference images from full-resolution frames.

    Reads frames at native resolution from the video files and computes the
    per-pixel absolute difference.
    """
    import cv2
    from progress.bar import Bar

    os.makedirs(diff_dir, exist_ok=True)

    pairs: list[tuple[int, int]] = []
    for diff in differences:
        # Before (boundary match)
        pairs.append((diff.a_range.start, diff.b_range.start))
        # First inner — only when both sides have gap frames
        if diff.first_inner_a and diff.first_inner_b:
            pairs.append((diff.first_inner_a.index, diff.first_inner_b.index))
        # Last inner — only when both sides have gap frames
        if diff.last_inner_a and diff.last_inner_b:
            pairs.append((diff.last_inner_a.index, diff.last_inner_b.index))
        # After (boundary match)
        pairs.append((diff.a_range.end, diff.b_range.end))

    # Filter out already-generated diffs
    to_generate = [
        (a, b) for a, b in pairs
        if not os.path.isfile(os.path.join(diff_dir, _diff_filename(a, b)))
    ]

    if not to_generate:
        return

    # Sort by movie A frame for efficient forward seeking
    to_generate.sort(key=lambda p: max(p[0], 0))

    cap_a = cv2.VideoCapture(movie_a)
    cap_b = cv2.VideoCapture(movie_b)
    try:
        with Bar("  Generating", max=len(to_generate)) as bar:
            for idx_a, idx_b in to_generate:
                frame_a = _read_frame_at(cap_a, idx_a)
                frame_b = _read_frame_at(cap_b, idx_b)

                if frame_a is not None and frame_b is not None:
                    if frame_a.shape != frame_b.shape:
                        frame_b = cv2.resize(frame_b, (frame_a.shape[1], frame_a.shape[0]))

                    diff_img = cv2.absdiff(frame_a, frame_b)
                    diff_img = cv2.normalize(diff_img, None, 0, 255, cv2.NORM_MINMAX)

                    out_path = os.path.join(diff_dir, _diff_filename(idx_a, idx_b))
                    cv2.imwrite(out_path, diff_img)

                bar.next()
    finally:
        cap_a.release()
        cap_b.release()


def _diff_img_tag(diff_dir: str, idx_a: int, idx_b: int) -> str:
    path = os.path.join(diff_dir, _diff_filename(idx_a, idx_b))
    return f'<img loading="lazy" src="{path}">'


def _collect_frames(
    differences: list[SceneDifference], contact_frames: int,
) -> tuple[list[int], list[int]]:
    """Collect all frame indices needed for both movies."""
    a_frames: list[int] = []
    b_frames: list[int] = []

    for diff in differences:
        # Before (boundary match) and After (boundary match)
        a_frames.extend([diff.a_range.start, diff.a_range.end])
        b_frames.extend([diff.b_range.start, diff.b_range.end])

        # First/Last inner frames
        if diff.first_inner_a:
            a_frames.append(diff.first_inner_a.index)
        if diff.first_inner_b:
            b_frames.append(diff.first_inner_b.index)
        if diff.last_inner_a:
            a_frames.append(diff.last_inner_a.index)
        if diff.last_inner_b:
            b_frames.append(diff.last_inner_b.index)

        # Contact sheet frames
        if diff.a_range.inner_count > 0:
            n = min(contact_frames, max(1, diff.a_range.inner_count))
            a_frames.extend(_sample_frames(diff.a_range, n))
        if diff.b_range.inner_count > 0:
            n = min(contact_frames, max(1, diff.b_range.inner_count))
            b_frames.extend(_sample_frames(diff.b_range, n))

    return a_frames, b_frames


def generate_report(
    differences: list[SceneDifference],
    movie_a: str, movie_b: str,
    label_a: str, label_b: str,
    output_path: str,
    frames_dir: str = "frames",
    contact_frames: int = 8,
):
    """Generate an HTML report referencing extracted frame images.

    Frames are extracted to subdirectories under frames_dir, then the HTML
    references them with relative paths. Re-running skips already-extracted frames.
    """
    a_frames_dir = os.path.join(frames_dir, label_a)
    b_frames_dir = os.path.join(frames_dir, label_b)
    a_clips_dir = os.path.join(frames_dir, "clips", label_a)
    b_clips_dir = os.path.join(frames_dir, "clips", label_b)

    # Collect and extract all needed frames
    a_frame_indices, b_frame_indices = _collect_frames(differences, contact_frames)

    print(f"Extracting {label_a} frames...")
    extract_frames(movie_a, a_frame_indices, a_frames_dir)
    print(f"Extracting {label_b} frames...")
    extract_frames(movie_b, b_frame_indices, b_frames_dir)

    print("Extracting clips...")
    extract_clips(differences, movie_a, movie_b, label_a, label_b,
                  os.path.join(frames_dir, "clips"))

    diff_images_dir = os.path.join(frames_dir, "diff")
    print("Generating boundary diffs...")
    _generate_diff_images(differences, movie_a, movie_b, diff_images_dir)

    # Generate HTML
    sections = []
    for i, diff in enumerate(differences):
        # Inner frames exist when there's more than 1 frame between boundary matches
        a_has_content = diff.a_range.inner_count > 0
        b_has_content = diff.b_range.inner_count > 0

        # Before = boundary match frame (start of range)
        before_a = _img_tag(a_frames_dir, diff.a_range.start)
        before_b = _img_tag(b_frames_dir, diff.b_range.start)
        before_diff = _diff_img_tag(diff_images_dir, diff.a_range.start, diff.b_range.start)

        # First inner frame — empty cell if that side has no gap frames
        first_a = _img_tag(a_frames_dir, diff.first_inner_a.index) if diff.first_inner_a else ""
        first_b = _img_tag(b_frames_dir, diff.first_inner_b.index) if diff.first_inner_b else ""
        if diff.first_inner_a and diff.first_inner_b:
            first_diff = _diff_img_tag(diff_images_dir, diff.first_inner_a.index, diff.first_inner_b.index)
        else:
            first_diff = ""

        # Last inner frame — empty cell if that side has no gap frames
        last_a = _img_tag(a_frames_dir, diff.last_inner_a.index) if diff.last_inner_a else ""
        last_b = _img_tag(b_frames_dir, diff.last_inner_b.index) if diff.last_inner_b else ""
        if diff.last_inner_a and diff.last_inner_b:
            last_diff = _diff_img_tag(diff_images_dir, diff.last_inner_a.index, diff.last_inner_b.index)
        else:
            last_diff = ""

        # After = boundary match frame (end of range)
        after_a = _img_tag(a_frames_dir, diff.a_range.end)
        after_b = _img_tag(b_frames_dir, diff.b_range.end)
        after_diff = _diff_img_tag(diff_images_dir, diff.a_range.end, diff.b_range.end)

        # Hash info from boundary matches — shown beneath each image
        # Build boundary cells — each cell has a standardized structure:
        #   <div class="b-cell">
        #     <img ...>               (or empty)
        #     <div class="b-frame">frame 12345</div>  (or empty)
        #     <div class="b-hd">↔ 3</div>             (or empty)
        #     <div class="b-adj">↓ 5</div>            (or empty)
        #   </div>
        def _bcell(img: str = "", frame: int | None = None,
                   cross_hd: float | None = None, adj_hd: float | None = None) -> str:
            parts = [f'<div class="b-cell">{img}']
            parts.append(f'<div class="b-frame">frame {frame}</div>' if frame is not None else '<div class="b-frame"></div>')
            parts.append(f'<div class="b-hd">&harr; {cross_hd:.0f}</div>' if cross_hd is not None else '<div class="b-hd"></div>')
            parts.append(f'<div class="b-adj">&darr; {adj_hd:.0f}</div>' if adj_hd is not None else '<div class="b-adj"></div>')
            parts.append('</div>')
            return ''.join(parts)

        sm = diff.start_match
        em = diff.end_match
        fia = diff.first_inner_a
        fib = diff.first_inner_b
        lia = diff.last_inner_a
        lib = diff.last_inner_b

        # Before row
        before_adj_a = hamming_distance(sm.a.hash, fia.hash) if sm and fia else None
        before_adj_b = hamming_distance(sm.b.hash, fib.hash) if sm and fib else None
        before_cross = hamming_distance(sm.a.hash, sm.b.hash) if sm else None
        cell_before_a = _bcell(before_a, sm.a.index if sm else None, adj_hd=before_adj_a)
        cell_before_b = _bcell(before_b, sm.b.index if sm else None, adj_hd=before_adj_b)
        cell_before_d = _bcell(before_diff, cross_hd=before_cross)

        # First row
        first_cross = hamming_distance(fia.hash, fib.hash) if fia and fib else None
        cell_first_a = _bcell(first_a, fia.index if fia else None)
        cell_first_b = _bcell(first_b, fib.index if fib else None)
        cell_first_d = _bcell(first_diff, cross_hd=first_cross)

        # Last row
        last_adj_a = hamming_distance(lia.hash, em.a.hash) if lia and em else None
        last_adj_b = hamming_distance(lib.hash, em.b.hash) if lib and em else None
        last_cross = hamming_distance(lia.hash, lib.hash) if lia and lib else None
        cell_last_a = _bcell(last_a, lia.index if lia else None, adj_hd=last_adj_a)
        cell_last_b = _bcell(last_b, lib.index if lib else None, adj_hd=last_adj_b)
        cell_last_d = _bcell(last_diff, cross_hd=last_cross)

        # After row
        after_cross = hamming_distance(em.a.hash, em.b.hash) if em else None
        cell_after_a = _bcell(after_a, em.a.index if em else None)
        cell_after_b = _bcell(after_b, em.b.index if em else None)
        cell_after_d = _bcell(after_diff, cross_hd=after_cross)

        # Min hamming distance across all boundary pairs for filtering.
        # Includes cross-edition (first A vs first B) and same-edition
        # adjacent frames (before A vs first A, etc.) to flag potential
        # boundary detection errors.
        # -1 means not applicable (no inner frames on either side).
        all_hds = []
        # Cross-edition: first/last inner frames
        if diff.first_inner_a and diff.first_inner_b:
            all_hds.append(hamming_distance(diff.first_inner_a.hash, diff.first_inner_b.hash))
        if diff.last_inner_a and diff.last_inner_b:
            all_hds.append(hamming_distance(diff.last_inner_a.hash, diff.last_inner_b.hash))
        # Same-edition adjacent: before vs first, last vs after
        if diff.start_match and diff.first_inner_a:
            all_hds.append(hamming_distance(diff.start_match.a.hash, diff.first_inner_a.hash))
        if diff.start_match and diff.first_inner_b:
            all_hds.append(hamming_distance(diff.start_match.b.hash, diff.first_inner_b.hash))
        if diff.end_match and diff.last_inner_a:
            all_hds.append(hamming_distance(diff.end_match.a.hash, diff.last_inner_a.hash))
        if diff.end_match and diff.last_inner_b:
            all_hds.append(hamming_distance(diff.end_match.b.hash, diff.last_inner_b.hash))
        min_inner_hd = min(all_hds) if all_hds else -1

        # Contact sheets
        cs_a = ""
        if a_has_content:
            n = min(contact_frames, max(1, diff.a_range.inner_count))
            for idx in _sample_frames(diff.a_range, n):
                cs_a += (
                    f'<div class="cs-frame">{_img_tag(a_frames_dir, idx)}'
                    f'<span class="cs-ts">{_ts(diff.to_time(idx))}</span></div>'
                )

        cs_b = ""
        if b_has_content:
            n = min(contact_frames, max(1, diff.b_range.inner_count))
            for idx in _sample_frames(diff.b_range, n):
                cs_b += (
                    f'<div class="cs-frame">{_img_tag(b_frames_dir, idx)}'
                    f'<span class="cs-ts">{_ts(diff.to_time(idx))}</span></div>'
                )

        type_cls = _type_class(diff.difference_type)
        type_lbl = _type_label(diff.difference_type)

        a_start_t = diff.to_time(diff.a_range.start).total_seconds()
        b_start_t = diff.to_time(diff.b_range.start).total_seconds()
        dur_frames = max(diff.a_range.inner_count, diff.b_range.inner_count)

        sections.append(f"""
    <details class="diff" data-type="{diff.difference_type}"
             data-a-start="{a_start_t}" data-b-start="{b_start_t}" data-duration="{dur_frames}"
             data-min-hd="{min_inner_hd:.0f}">
      <summary class="{type_cls}">
        <span class="diff-num">#{i + 1}</span>
        <span class="diff-type {type_cls}">{type_lbl}</span>
        <span class="diff-meta">
          <span class="meta-a">{label_a}: {_ts(diff.to_time(diff.a_range.start)) + "&ndash;" + _ts(diff.to_time(diff.a_range.end)) + " (" + _dur(diff.a_range.inner_count, diff.fps) + ")" if diff.a_range.inner_count > 0 else _ts(diff.to_time(diff.a_range.start))}</span>
          <span class="meta-sep">|</span>
          <span class="meta-b">{label_b}: {_ts(diff.to_time(diff.b_range.start)) + "&ndash;" + _ts(diff.to_time(diff.b_range.end)) + " (" + _dur(diff.b_range.inner_count, diff.fps) + ")" if diff.b_range.inner_count > 0 else _ts(diff.to_time(diff.b_range.start))}</span>
        </span>
      </summary>
      <div class="diff-body">
        <h3>Boundary Verification</h3>
        <p class="hint">Before/After are the last/first matching frames. First/Last are the start/end of the difference.</p>
        <div class="boundary-grid">
          <div class="b-label"></div><div class="b-label">{label_a}</div><div class="b-label">{label_b}</div><div class="b-label">Difference</div>
          <div class="b-row-label">Before</div>{cell_before_a}{cell_before_b}{cell_before_d}
          <div class="b-row-label">First</div>{cell_first_a}{cell_first_b}{cell_first_d}
          <div class="b-row-label">Last</div>{cell_last_a}{cell_last_b}{cell_last_d}
          <div class="b-row-label">After</div>{cell_after_a}{cell_after_b}{cell_after_d}
        </div>
        {"<h3>Content &mdash; " + label_a + "</h3><div class='contact-sheet'>" + cs_a + "</div>" if cs_a else ""}
        {"<h3>Content &mdash; " + label_b + "</h3><div class='contact-sheet'>" + cs_b + "</div>" if cs_b else ""}
        {"<h3>Video</h3><div class='video-row' data-sync>" if a_has_content or b_has_content else ""}
          {"<div class='video-col'><h4>" + label_a + "</h4><video controls preload='metadata' src='" + os.path.join(a_clips_dir, _clip_filename(diff.a_range.start, diff.a_range.end)) + "'></video></div>" if a_has_content else ""}
          {"<div class='video-col'><h4>" + label_b + "</h4><video controls preload='metadata' src='" + os.path.join(b_clips_dir, _clip_filename(diff.b_range.start, diff.b_range.end)) + "'></video></div>" if b_has_content else ""}
        {"<div class='sync-controls'><button class='sync-btn' onclick='toggleSync(this)'>Sync: ON</button></div></div>" if a_has_content and b_has_content else "</div>" if a_has_content or b_has_content else ""}
      </div>
    </details>""")

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Edition Comparison Report</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: system-ui, sans-serif; background: #1a1a1a; color: #e0e0e0; padding: 20px; }}
  h1 {{ margin-bottom: 8px; }}
  .subtitle {{ color: #888; margin-bottom: 24px; }}
  details {{ margin-bottom: 8px; border: 1px solid #333; border-radius: 6px; overflow: hidden; }}
  summary {{ padding: 12px 16px; cursor: pointer; background: #222; display: grid; grid-template-columns: 3em 7em 1fr; align-items: center; gap: 8px; }}
  summary:hover {{ background: #2a2a2a; }}
  .diff-num {{ color: #666; font-family: monospace; min-width: 3em; }}
  .diff-type {{ padding: 2px 8px; border-radius: 4px; font-size: 0.85em; font-weight: 600; }}
  .type-added {{ background: #1a3a1a; color: #4ade80; }}
  .type-removed {{ background: #3a1a1a; color: #f87171; }}
  .type-modified {{ background: #3a3a1a; color: #facc15; }}
  .type-reordered {{ background: #1a2a3a; color: #60a5fa; }}
  .diff-meta {{ color: #888; font-size: 0.85em; font-family: monospace; display: grid; grid-template-columns: 65ch auto 1fr; align-items: center; gap: 8px; }}
  .meta-sep {{ color: #444; }}
  .diff-body {{ padding: 16px; }}
  h3 {{ margin: 16px 0 8px; color: #aaa; font-size: 0.95em; text-transform: uppercase; letter-spacing: 0.05em; }}
  h3:first-child {{ margin-top: 0; }}
  .hint {{ color: #666; font-size: 0.8em; margin-bottom: 8px; }}
  .boundary-grid {{ display: grid; grid-template-columns: auto 1fr 1fr 1fr; gap: 8px 16px; align-items: start; }}
  .b-label {{ color: #aaa; font-weight: normal; font-size: 0.85em; text-align: center; padding-bottom: 4px; }}
  .b-row-label {{ color: #666; font-size: 0.85em; text-align: right; padding-top: 4px; align-self: start; }}
  .b-cell {{ text-align: center; }}
  .b-cell img {{ max-width: 100%; border-radius: 4px; aspect-ratio: 2.39; object-fit: cover; }}
  .b-frame {{ font-family: monospace; font-size: 0.85em; color: #666; margin-top: 4px; min-height: 1.2em; }}
  .b-hd {{ font-family: monospace; font-size: 2em; color: #888; min-height: 1.5em; }}
  .b-hd strong {{ color: #e0e0e0; }}
  .b-adj {{ font-family: monospace; font-size: 2em; color: #888; text-align: right; min-height: 1.5em; }}
  .b-adj strong {{ color: #e0e0e0; }}
  .contact-sheet {{ display: flex; flex-wrap: wrap; gap: 6px; }}
  .cs-frame {{ display: flex; flex-direction: column; align-items: center; }}
  .cs-frame img {{ max-width: 480px; border-radius: 4px; aspect-ratio: 2.39; object-fit: cover; }}
  .cs-ts {{ font-size: 0.7em; color: #666; font-family: monospace; margin-top: 2px; }}
  .controls {{ display: flex; gap: 16px; align-items: center; margin-bottom: 20px; padding: 12px 16px; background: #222; border-radius: 6px; flex-wrap: wrap; }}
  .controls label {{ color: #aaa; font-size: 0.85em; }}
  .controls select {{ background: #333; color: #e0e0e0; border: 1px solid #555; border-radius: 4px; padding: 4px 8px; font-size: 0.85em; }}
  .controls .filter-group {{ display: flex; gap: 8px; align-items: center; }}
  .controls .filter-btn {{ background: #333; color: #e0e0e0; border: 1px solid #555; border-radius: 4px; padding: 4px 10px; font-size: 0.85em; cursor: pointer; }}
  .controls .filter-btn.active {{ border-color: #888; background: #444; }}
  .controls .filter-btn.type-added.active {{ border-color: #4ade80; }}
  .controls .filter-btn.type-removed.active {{ border-color: #f87171; }}
  .controls .filter-btn.type-modified.active {{ border-color: #facc15; }}
  .controls .filter-btn.type-reordered.active {{ border-color: #60a5fa; }}
  .diff.hidden {{ display: none; }}
  .hamming-group {{ display: flex; align-items: center; gap: 8px; }}
  .hamming-group input[type=range] {{ width: 120px; accent-color: #60a5fa; }}
  #hamming-value {{ color: #e0e0e0; font-family: monospace; min-width: 2ch; }}
  .video-row {{ display: flex; gap: 16px; flex-wrap: wrap; align-items: flex-start; }}
  .video-col {{ flex: 1; min-width: 300px; }}
  .video-col h4 {{ color: #aaa; font-size: 0.85em; margin-bottom: 6px; font-weight: normal; }}
  .video-col video {{ width: 100%; border-radius: 4px; }}
  .sync-controls {{ flex-basis: 100%; }}
  .sync-btn {{ background: #333; color: #4ade80; border: 1px solid #4ade80; border-radius: 4px; padding: 4px 12px; font-size: 0.85em; cursor: pointer; }}
  .sync-btn.off {{ color: #666; border-color: #555; }}
</style>
</head>
<body>
  <h1>Edition Comparison Report</h1>
  <p class="subtitle">{label_a} vs {label_b} &mdash; {len(differences)} differences</p>
  <div class="controls">
    <label>Sort by:</label>
    <select id="sort-select">
      <option value="b-start" selected>Timestamp ({label_b})</option>
      <option value="a-start">Timestamp ({label_a})</option>
      <option value="duration">Duration</option>
    </select>
    <label>Filter:</label>
    <div class="filter-group">
      <button class="filter-btn type-modified active" data-type="modified">Modified</button>
      <button class="filter-btn type-added active" data-type="unique_to_b">Added in B</button>
      <button class="filter-btn type-removed active" data-type="unique_to_a">Only in A</button>
      <button class="filter-btn type-reordered active" data-type="reordered">Reordered</button>
    </div>
    <label>Max hamming:</label>
    <div class="hamming-group">
      <input type="range" id="hamming-slider" min="0" max="50" value="50">
      <span id="hamming-value">50</span>
      <button id="hamming-unlimited" class="filter-btn active">&#x221e;</button>
    </div>
  </div>
  <div id="diff-container">
  {"".join(sections)}
  </div>
<script>
(function() {{
  const container = document.getElementById('diff-container');
  const sortSelect = document.getElementById('sort-select');
  const filterBtns = document.querySelectorAll('.filter-btn[data-type]');
  const hammingSlider = document.getElementById('hamming-slider');
  const hammingValue = document.getElementById('hamming-value');
  const hammingUnlimited = document.getElementById('hamming-unlimited');

  let hammingLimit = Infinity;

  function getActiveTypes() {{
    return new Set(
      Array.from(filterBtns).filter(b => b.classList.contains('active')).map(b => b.dataset.type)
    );
  }}

  function applySort() {{
    const key = sortSelect.value;
    const items = Array.from(container.querySelectorAll('.diff'));
    items.sort((a, b) => {{
      const av = parseFloat(a.dataset[key === 'b-start' ? 'bStart' : key === 'a-start' ? 'aStart' : 'duration']);
      const bv = parseFloat(b.dataset[key === 'b-start' ? 'bStart' : key === 'a-start' ? 'aStart' : 'duration']);
      return av - bv;
    }});
    items.forEach(el => container.appendChild(el));
  }}

  function applyFilter() {{
    const active = getActiveTypes();
    container.querySelectorAll('.diff').forEach(el => {{
      const typeMatch = active.has(el.dataset.type);
      const hd = parseFloat(el.dataset.minHd);
      const hdMatch = hd < 0 || hd <= hammingLimit;
      el.classList.toggle('hidden', !typeMatch || !hdMatch);
    }});
  }}

  sortSelect.addEventListener('change', applySort);
  filterBtns.forEach(btn => {{
    btn.addEventListener('click', () => {{
      btn.classList.toggle('active');
      applyFilter();
    }});
  }});

  hammingSlider.addEventListener('input', () => {{
    hammingLimit = parseInt(hammingSlider.value);
    hammingValue.textContent = hammingLimit;
    hammingUnlimited.classList.remove('active');
    applyFilter();
  }});

  hammingUnlimited.addEventListener('click', () => {{
    const isActive = hammingUnlimited.classList.toggle('active');
    if (isActive) {{
      hammingLimit = Infinity;
      hammingValue.textContent = '\u221e';
    }} else {{
      hammingLimit = parseInt(hammingSlider.value);
      hammingValue.textContent = hammingLimit;
    }}
    applyFilter();
  }});

  applySort();
}})();

function toggleSync(btn) {{
  const row = btn.closest('[data-sync]');
  const videos = row.querySelectorAll('video');
  if (videos.length < 2) return;

  const isOn = !btn.classList.contains('off');
  if (isOn) {{
    btn.classList.add('off');
    btn.textContent = 'Sync: OFF';
    videos.forEach(v => {{ v._syncHandler && v.removeEventListener('play', v._syncHandler); v._syncPause && v.removeEventListener('pause', v._syncPause); v._syncSeek && v.removeEventListener('seeked', v._syncSeek); }});
  }} else {{
    btn.classList.remove('off');
    btn.textContent = 'Sync: ON';
    setupSync(videos);
  }}
}}

function setupSync(videos) {{
  const [a, b] = videos;
  let syncing = false;

  function syncPlay(source, target) {{
    return () => {{ if (!syncing) {{ syncing = true; target.play().finally(() => syncing = false); }} }};
  }}
  function syncPause(source, target) {{
    return () => {{ if (!syncing) {{ syncing = true; target.pause(); syncing = false; }} }};
  }}
  function syncSeek(source, target) {{
    return () => {{ if (!syncing) {{ syncing = true; target.currentTime = source.currentTime; syncing = false; }} }};
  }}

  a._syncHandler = syncPlay(a, b); a.addEventListener('play', a._syncHandler);
  b._syncHandler = syncPlay(b, a); b.addEventListener('play', b._syncHandler);
  a._syncPause = syncPause(a, b); a.addEventListener('pause', a._syncPause);
  b._syncPause = syncPause(b, a); b.addEventListener('pause', b._syncPause);
  a._syncSeek = syncSeek(a, b); a.addEventListener('seeked', a._syncSeek);
  b._syncSeek = syncSeek(b, a); b.addEventListener('seeked', b._syncSeek);
}}

document.querySelectorAll('[data-sync]').forEach(row => {{
  const videos = row.querySelectorAll('video');
  if (videos.length === 2) setupSync(videos);
}});
</script>
</body>
</html>"""

    with open(output_path, "w") as f:
        f.write(html)
    print(f"Report written to {output_path}")
