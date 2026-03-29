"""Generate an HTML visual verification report for scene differences."""

import os
from datetime import timedelta

from movie_edition_comparer.comparison import hamming_distance
from movie_edition_comparer.models import DifferenceType, SceneDifference, TimeRange
from movie_edition_comparer.video import _frame_filename, extract_frames

ZERO = timedelta(0)
ONE_FRAME = timedelta(milliseconds=42)  # ~1 frame at 23.976 fps


def _ts(t: timedelta) -> str:
    total = int(t.total_seconds())
    h, remainder = divmod(total, 3600)
    m, s = divmod(remainder, 60)
    return f"{h}:{m:02d}:{s:02d}"


def _sample_timestamps(time_range: TimeRange, n: int) -> list[timedelta]:
    """Return n evenly-spaced timestamps within the range (excluding endpoints)."""
    if time_range.duration <= ZERO or n <= 0:
        return []
    if n == 1:
        return [time_range.start + time_range.duration / 2]
    step = time_range.duration / (n + 1)
    return [time_range.start + step * (i + 1) for i in range(n)]


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


def _img_tag(frames_dir: str, timestamp: timedelta) -> str:
    """Return an <img> tag referencing a frame file, relative to the report."""
    path = os.path.join(frames_dir, _frame_filename(max(timestamp, ZERO)))
    return f'<img src="{path}">'


def _diff_filename(ts_a: timedelta, ts_b: timedelta) -> str:
    ms_a = int(max(ts_a, ZERO).total_seconds() * 1000)
    ms_b = int(max(ts_b, ZERO).total_seconds() * 1000)
    return f"diff_{ms_a:012d}_{ms_b:012d}.png"


def _read_frame_at(cap, timestamp: timedelta):
    """Seek and read a single frame from an open VideoCapture."""
    import cv2
    cap.set(cv2.CAP_PROP_POS_MSEC, max(timestamp, ZERO).total_seconds() * 1000)
    ret, frame = cap.read()
    return frame if ret else None


def _generate_diff_images(
    differences: list[SceneDifference],
    movie_a: str, movie_b: str,
    diff_dir: str, thumbnail_width: int,
):
    """Generate difference images from full-resolution frames.

    Reads frames at native resolution from the video files, computes the
    per-pixel absolute difference, then downscales the result for the report.
    """
    import cv2
    from progress.bar import Bar

    os.makedirs(diff_dir, exist_ok=True)

    pairs = []
    for diff in differences:
        pairs.append((diff.a_range.start - ONE_FRAME, diff.b_range.start - ONE_FRAME))
        pairs.append((diff.a_range.start, diff.b_range.start))
        pairs.append((diff.a_range.end, diff.b_range.end))
        pairs.append((diff.a_range.end + ONE_FRAME, diff.b_range.end + ONE_FRAME))

    # Filter out already-generated diffs
    to_generate = [
        (ts_a, ts_b) for ts_a, ts_b in pairs
        if not os.path.isfile(os.path.join(diff_dir, _diff_filename(ts_a, ts_b)))
    ]

    if not to_generate:
        return

    # Sort by movie A timestamp for efficient forward seeking
    to_generate.sort(key=lambda p: max(p[0], ZERO))

    cap_a = cv2.VideoCapture(movie_a)
    cap_b = cv2.VideoCapture(movie_b)
    try:
        with Bar("  Generating", max=len(to_generate)) as bar:
            for ts_a, ts_b in to_generate:
                frame_a = _read_frame_at(cap_a, ts_a)
                frame_b = _read_frame_at(cap_b, ts_b)

                if frame_a is not None and frame_b is not None:
                    if frame_a.shape != frame_b.shape:
                        frame_b = cv2.resize(frame_b, (frame_a.shape[1], frame_a.shape[0]))

                    diff_img = cv2.absdiff(frame_a, frame_b)
                    diff_img = cv2.normalize(diff_img, None, 0, 255, cv2.NORM_MINMAX)

                    # Downscale for the report
                    h, w = diff_img.shape[:2]
                    if w != thumbnail_width:
                        scale = thumbnail_width / w
                        new_h = int(h * scale)
                        diff_img = cv2.resize(diff_img, (thumbnail_width, new_h),
                                              interpolation=cv2.INTER_AREA)

                    out_path = os.path.join(diff_dir, _diff_filename(ts_a, ts_b))
                    cv2.imwrite(out_path, diff_img)

                bar.next()
    finally:
        cap_a.release()
        cap_b.release()


def _diff_img_tag(diff_dir: str, ts_a: timedelta, ts_b: timedelta) -> str:
    path = os.path.join(diff_dir, _diff_filename(ts_a, ts_b))
    return f'<img src="{path}">'


def _collect_timestamps(
    differences: list[SceneDifference], contact_frames: int,
) -> tuple[list[timedelta], list[timedelta]]:
    """Collect all timestamps needed for both movies."""
    a_timestamps: list[timedelta] = []
    b_timestamps: list[timedelta] = []

    for diff in differences:
        # Boundary frames (outer + inner)
        a_timestamps.extend([
            diff.a_range.start - ONE_FRAME, diff.a_range.start,
            diff.a_range.end, diff.a_range.end + ONE_FRAME,
        ])
        b_timestamps.extend([
            diff.b_range.start - ONE_FRAME, diff.b_range.start,
            diff.b_range.end, diff.b_range.end + ONE_FRAME,
        ])

        # Contact sheet frames
        if diff.a_range.duration > ZERO:
            n = min(contact_frames, max(1, int(diff.a_range.duration / ONE_FRAME)))
            a_timestamps.extend(_sample_timestamps(diff.a_range, n))
        if diff.b_range.duration > ZERO:
            n = min(contact_frames, max(1, int(diff.b_range.duration / ONE_FRAME)))
            b_timestamps.extend(_sample_timestamps(diff.b_range, n))

    return a_timestamps, b_timestamps


def generate_report(
    differences: list[SceneDifference],
    movie_a: str, movie_b: str,
    label_a: str, label_b: str,
    output_path: str,
    frames_dir: str = "frames",
    contact_frames: int = 8,
    thumbnail_width: int = 320,
):
    """Generate an HTML report referencing extracted frame images.

    Frames are extracted to subdirectories under frames_dir, then the HTML
    references them with relative paths. Re-running skips already-extracted frames.
    """
    a_frames_dir = os.path.join(frames_dir, label_a)
    b_frames_dir = os.path.join(frames_dir, label_b)

    # Collect and extract all needed frames
    a_timestamps, b_timestamps = _collect_timestamps(differences, contact_frames)

    print(f"Extracting {label_a} frames...")
    extract_frames(movie_a, a_timestamps, a_frames_dir, width=thumbnail_width)
    print(f"Extracting {label_b} frames...")
    extract_frames(movie_b, b_timestamps, b_frames_dir, width=thumbnail_width)

    diff_images_dir = os.path.join(frames_dir, "diff")
    print("Generating boundary diffs...")
    _generate_diff_images(differences, movie_a, movie_b, diff_images_dir, thumbnail_width)

    # Generate HTML
    sections = []
    for i, diff in enumerate(differences):
        a_has_content = diff.a_range.duration > ZERO
        b_has_content = diff.b_range.duration > ZERO

        before_a = _img_tag(a_frames_dir, diff.a_range.start - ONE_FRAME)
        before_b = _img_tag(b_frames_dir, diff.b_range.start - ONE_FRAME)
        before_diff = _diff_img_tag(diff_images_dir,
                                    diff.a_range.start - ONE_FRAME,
                                    diff.b_range.start - ONE_FRAME)
        first_a = _img_tag(a_frames_dir, diff.a_range.start)
        first_b = _img_tag(b_frames_dir, diff.b_range.start)
        first_diff = _diff_img_tag(diff_images_dir,
                                   diff.a_range.start,
                                   diff.b_range.start)
        last_a = _img_tag(a_frames_dir, diff.a_range.end)
        last_b = _img_tag(b_frames_dir, diff.b_range.end)
        last_diff = _diff_img_tag(diff_images_dir,
                                  diff.a_range.end,
                                  diff.b_range.end)
        after_a = _img_tag(a_frames_dir, diff.a_range.end + ONE_FRAME)
        after_b = _img_tag(b_frames_dir, diff.b_range.end + ONE_FRAME)
        after_diff = _diff_img_tag(diff_images_dir,
                                   diff.a_range.end + ONE_FRAME,
                                   diff.b_range.end + ONE_FRAME)

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
            n = min(contact_frames, max(1, int(diff.a_range.duration / ONE_FRAME)))
            for ts in _sample_timestamps(diff.a_range, n):
                cs_a += (
                    f'<div class="cs-frame">{_img_tag(a_frames_dir, ts)}'
                    f'<span class="cs-ts">{_ts(ts)}</span></div>'
                )

        cs_b = ""
        if b_has_content:
            n = min(contact_frames, max(1, int(diff.b_range.duration / ONE_FRAME)))
            for ts in _sample_timestamps(diff.b_range, n):
                cs_b += (
                    f'<div class="cs-frame">{_img_tag(b_frames_dir, ts)}'
                    f'<span class="cs-ts">{_ts(ts)}</span></div>'
                )

        type_cls = _type_class(diff.difference_type)
        type_lbl = _type_label(diff.difference_type)

        a_start_s = diff.a_range.start.total_seconds()
        b_start_s = diff.b_range.start.total_seconds()
        dur_s = max(diff.a_range.duration, diff.b_range.duration).total_seconds()

        sections.append(f"""
    <details class="diff" data-type="{diff.difference_type}"
             data-a-start="{a_start_s}" data-b-start="{b_start_s}" data-duration="{dur_s}">
      <summary class="{type_cls}">
        <span class="diff-num">#{i + 1}</span>
        <span class="diff-type {type_cls}">{type_lbl}</span>
        <span class="diff-meta">
          {label_a}: {_ts(diff.a_range.start)}&ndash;{_ts(diff.a_range.end)} ({_ts(diff.a_range.duration)})
          &nbsp;|&nbsp;
          {label_b}: {_ts(diff.b_range.start)}&ndash;{_ts(diff.b_range.end)} ({_ts(diff.b_range.duration)})
        </span>
      </summary>
      <div class="diff-body">
        <h3>Boundary Verification</h3>
        <p class="hint">Before/After are the last/first matching frames. First/Last are the start/end of the difference. HD = hamming distance (0 = identical hash).</p>
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
  table.boundary img {{ max-width: {thumbnail_width}px; border-radius: 4px; }}
  .contact-sheet {{ display: flex; flex-wrap: wrap; gap: 6px; }}
  .cs-frame {{ display: flex; flex-direction: column; align-items: center; }}
  .cs-frame img {{ max-width: {thumbnail_width}px; border-radius: 4px; }}
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
