"""Generate an HTML visual verification report for scene differences."""

import os
from datetime import timedelta

from movie_edition_comparer.comparison import hamming_distance
from movie_edition_comparer.models import DifferenceType, FrameRange, SceneDifference
from movie_edition_comparer.video import _frame_filename, extract_frames


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
    return f'<img src="{path}">'


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
    return f'<img src="{path}">'


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
        if diff.a_range.frame_count > 0:
            n = min(contact_frames, max(1, diff.a_range.frame_count))
            a_frames.extend(_sample_frames(diff.a_range, n))
        if diff.b_range.frame_count > 0:
            n = min(contact_frames, max(1, diff.b_range.frame_count))
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

    # Collect and extract all needed frames
    a_frame_indices, b_frame_indices = _collect_frames(differences, contact_frames)

    print(f"Extracting {label_a} frames...")
    extract_frames(movie_a, a_frame_indices, a_frames_dir)
    print(f"Extracting {label_b} frames...")
    extract_frames(movie_b, b_frame_indices, b_frames_dir)

    diff_images_dir = os.path.join(frames_dir, "diff")
    print("Generating boundary diffs...")
    _generate_diff_images(differences, movie_a, movie_b, diff_images_dir)

    # Generate HTML
    sections = []
    for i, diff in enumerate(differences):
        # Inner frames exist when there's more than 1 frame between boundary matches
        a_has_content = diff.a_range.frame_count > 1
        b_has_content = diff.b_range.frame_count > 1

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
        start_a_hash = start_b_hash = start_diff_hash = ""
        end_a_hash = end_b_hash = end_diff_hash = ""
        if diff.start_match:
            sm = diff.start_match
            start_hd = hamming_distance(sm.a.hash, sm.b.hash)
            start_a_hash = f'<span class="hash-label">frame {sm.a.index}</span>'
            start_b_hash = f'<span class="hash-label">frame {sm.b.index}</span>'
            start_diff_hash = f'<span class="hash-label">hamming: <strong>{start_hd:.0f}</strong></span>'
        if diff.end_match:
            em = diff.end_match
            end_hd = hamming_distance(em.a.hash, em.b.hash)
            end_a_hash = f'<span class="hash-label">frame {em.a.index}</span>'
            end_b_hash = f'<span class="hash-label">frame {em.b.index}</span>'
            end_diff_hash = f'<span class="hash-label">hamming: <strong>{end_hd:.0f}</strong></span>'

        first_a_label = first_b_label = first_diff_label = ""
        last_a_label = last_b_label = last_diff_label = ""
        if diff.first_inner_a:
            first_a_label = f'<span class="hash-label">frame {diff.first_inner_a.index}</span>'
        if diff.first_inner_b:
            first_b_label = f'<span class="hash-label">frame {diff.first_inner_b.index}</span>'
        if diff.first_inner_a and diff.first_inner_b:
            first_hd = hamming_distance(diff.first_inner_a.hash, diff.first_inner_b.hash)
            first_diff_label = f'<span class="hash-label">hamming: <strong>{first_hd:.0f}</strong></span>'
        if diff.last_inner_a:
            last_a_label = f'<span class="hash-label">frame {diff.last_inner_a.index}</span>'
        if diff.last_inner_b:
            last_b_label = f'<span class="hash-label">frame {diff.last_inner_b.index}</span>'
        if diff.last_inner_a and diff.last_inner_b:
            last_hd = hamming_distance(diff.last_inner_a.hash, diff.last_inner_b.hash)
            last_diff_label = f'<span class="hash-label">hamming: <strong>{last_hd:.0f}</strong></span>'

        # Contact sheets
        cs_a = ""
        if a_has_content:
            n = min(contact_frames, max(1, diff.a_range.frame_count))
            for idx in _sample_frames(diff.a_range, n):
                cs_a += (
                    f'<div class="cs-frame">{_img_tag(a_frames_dir, idx)}'
                    f'<span class="cs-ts">{_ts(diff.to_time(idx))}</span></div>'
                )

        cs_b = ""
        if b_has_content:
            n = min(contact_frames, max(1, diff.b_range.frame_count))
            for idx in _sample_frames(diff.b_range, n):
                cs_b += (
                    f'<div class="cs-frame">{_img_tag(b_frames_dir, idx)}'
                    f'<span class="cs-ts">{_ts(diff.to_time(idx))}</span></div>'
                )

        type_cls = _type_class(diff.difference_type)
        type_lbl = _type_label(diff.difference_type)

        a_start_t = diff.to_time(diff.a_range.start).total_seconds()
        b_start_t = diff.to_time(diff.b_range.start).total_seconds()
        dur_frames = max(diff.a_range.frame_count, diff.b_range.frame_count)

        sections.append(f"""
    <details class="diff" data-type="{diff.difference_type}"
             data-a-start="{a_start_t}" data-b-start="{b_start_t}" data-duration="{dur_frames}">
      <summary class="{type_cls}">
        <span class="diff-num">#{i + 1}</span>
        <span class="diff-type {type_cls}">{type_lbl}</span>
        <span class="diff-meta">
          {label_a}: {_ts(diff.to_time(diff.a_range.start))}&ndash;{_ts(diff.to_time(diff.a_range.end))} ({_dur(diff.a_range.frame_count, diff.fps)})
          &nbsp;|&nbsp;
          {label_b}: {_ts(diff.to_time(diff.b_range.start))}&ndash;{_ts(diff.to_time(diff.b_range.end))} ({_dur(diff.b_range.frame_count, diff.fps)})
        </span>
      </summary>
      <div class="diff-body">
        <h3>Boundary Verification</h3>
        <p class="hint">Before/After are the last/first matching frames. First/Last are the start/end of the difference.</p>
        <table class="boundary">
          <tr><th></th><th>{label_a}</th><th>{label_b}</th><th>Difference</th></tr>
          <tr><td>Before</td><td>{before_a}{start_a_hash}</td><td>{before_b}{start_b_hash}</td><td>{before_diff}{start_diff_hash}</td></tr>
          <tr><td>First</td><td>{first_a}{first_a_label}</td><td>{first_b}{first_b_label}</td><td>{first_diff}{first_diff_label}</td></tr>
          <tr><td>Last</td><td>{last_a}{last_a_label}</td><td>{last_b}{last_b_label}</td><td>{last_diff}{last_diff_label}</td></tr>
          <tr><td>After</td><td>{after_a}{end_a_hash}</td><td>{after_b}{end_b_hash}</td><td>{after_diff}{end_diff_hash}</td></tr>
        </table>
        {"<h3>Content &mdash; " + label_a + "</h3><div class='contact-sheet'>" + cs_a + "</div>" if cs_a else ""}
        {"<h3>Content &mdash; " + label_b + "</h3><div class='contact-sheet'>" + cs_b + "</div>" if cs_b else ""}
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
  summary {{ padding: 12px 16px; cursor: pointer; background: #222; display: flex; align-items: center; gap: 12px; }}
  summary:hover {{ background: #2a2a2a; }}
  .diff-num {{ color: #666; font-family: monospace; min-width: 3em; }}
  .diff-type {{ padding: 2px 8px; border-radius: 4px; font-size: 0.85em; font-weight: 600; }}
  .type-added {{ background: #1a3a1a; color: #4ade80; }}
  .type-removed {{ background: #3a1a1a; color: #f87171; }}
  .type-modified {{ background: #3a3a1a; color: #facc15; }}
  .type-reordered {{ background: #1a2a3a; color: #60a5fa; }}
  .diff-meta {{ color: #888; font-size: 0.85em; font-family: monospace; }}
  .diff-body {{ padding: 16px; }}
  h3 {{ margin: 16px 0 8px; color: #aaa; font-size: 0.95em; text-transform: uppercase; letter-spacing: 0.05em; }}
  h3:first-child {{ margin-top: 0; }}
  .hint {{ color: #666; font-size: 0.8em; margin-bottom: 8px; }}
  table.boundary {{ border-collapse: collapse; }}
  table.boundary td, table.boundary th {{ padding: 6px 10px; text-align: center; vertical-align: middle; }}
  table.boundary th {{ color: #aaa; font-weight: normal; }}
  table.boundary td:first-child {{ color: #666; font-size: 0.85em; text-align: right; }}
  table.boundary img {{ max-width: 480px; border-radius: 4px; }}
  .contact-sheet {{ display: flex; flex-wrap: wrap; gap: 6px; }}
  .cs-frame {{ display: flex; flex-direction: column; align-items: center; }}
  .cs-frame img {{ max-width: 480px; border-radius: 4px; }}
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
  .hash-label {{ font-size: 0.8em; color: #666; display: block; margin-top: 4px; font-family: monospace; }}
  .hash-label strong {{ color: #e0e0e0; font-size: 1.2em; }}
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
  </div>
  <div id="diff-container">
  {"".join(sections)}
  </div>
<script>
(function() {{
  const container = document.getElementById('diff-container');
  const sortSelect = document.getElementById('sort-select');
  const filterBtns = document.querySelectorAll('.filter-btn');

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
      el.classList.toggle('hidden', !active.has(el.dataset.type));
    }});
  }}

  sortSelect.addEventListener('change', applySort);
  filterBtns.forEach(btn => {{
    btn.addEventListener('click', () => {{
      btn.classList.toggle('active');
      applyFilter();
    }});
  }});

  applySort();
}})();
</script>
</body>
</html>"""

    with open(output_path, "w") as f:
        f.write(html)
    print(f"Report written to {output_path}")
