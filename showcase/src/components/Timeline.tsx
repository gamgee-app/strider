import { useMemo, useRef, useEffect } from "react";
import type { Difference, FilmData } from "../types";
import { typeColor } from "../utils";

interface TimelineProps {
  data: FilmData;
  selected: Difference | null;
  onSelect: (diff: Difference) => void;
}

const TIMELINE_WIDTH = 2000;
const PAD = 1000; // padding on each side so edges can center
const TOTAL_WIDTH = TIMELINE_WIDTH + PAD * 2;
const CHAPTER_A_Y = 30;
const LINE_Y_A = 70;
const LINE_Y_B = 100;
const CHAPTER_B_Y = 140;
const SVG_HEIGHT = 170;
const MARK_MIN_WIDTH = 3;

interface DiffMark {
  x: number;
  width: number;
  diff: Difference;
}

interface BreakRegion {
  x: number;
  width: number;
}

interface ChapterMark {
  x: number;
  title: string;
}

function buildLayout(data: FilmData) {
  const diffs = data.differences;
  const totalA = data.film.theatrical_frames;
  const totalB = data.film.extended_frames;

  let totalLogical = 0;
  let prevAEnd = 0;
  let prevBEnd = 0;

  const segments: Array<
    | { type: "match"; aFrames: number; bFrames: number }
    | { type: "diff"; aFrames: number; bFrames: number; diff: Difference }
  > = [];

  for (const diff of diffs) {
    const matchA = diff.theatrical.start_frame - prevAEnd;
    const matchB = diff.extended.start_frame - prevBEnd;
    const matchFrames = Math.max(matchA, matchB, 0);
    if (matchFrames > 0) {
      segments.push({ type: "match", aFrames: matchA, bFrames: matchB });
      totalLogical += matchFrames;
    }

    const aFrames = Math.max(0, diff.theatrical.end_frame - diff.theatrical.start_frame);
    const bFrames = Math.max(0, diff.extended.end_frame - diff.extended.start_frame);
    const diffFrames = Math.max(aFrames, bFrames, 1);
    segments.push({ type: "diff", aFrames, bFrames, diff });
    totalLogical += diffFrames;

    prevAEnd = diff.theatrical.end_frame;
    prevBEnd = diff.extended.end_frame;
  }

  const trailA = totalA - prevAEnd;
  const trailB = totalB - prevBEnd;
  const trailFrames = Math.max(trailA, trailB, 0);
  if (trailFrames > 0) {
    segments.push({ type: "match", aFrames: trailA, bFrames: trailB });
    totalLogical += trailFrames;
  }

  const scale = TIMELINE_WIDTH / totalLogical;

  const aMarks: DiffMark[] = [];
  const bMarks: DiffMark[] = [];
  const aBreaks: BreakRegion[] = [];
  const bBreaks: BreakRegion[] = [];
  let x = 0;

  // Track cumulative frames per edition for chapter mapping
  let cumA = 0;
  let cumB = 0;
  const aCheckpoints: Array<[number, number]> = [[0, 0]];
  const bCheckpoints: Array<[number, number]> = [[0, 0]];

  for (const seg of segments) {
    if (seg.type === "match") {
      const segWidth = Math.max(seg.aFrames, seg.bFrames) * scale;
      aCheckpoints.push([cumA, x]);
      bCheckpoints.push([cumB, x]);
      cumA += seg.aFrames;
      cumB += seg.bFrames;
      x += segWidth;
    } else {
      const maxFrames = Math.max(seg.aFrames, seg.bFrames, 1);
      const segWidth = Math.max(MARK_MIN_WIDTH, maxFrames * scale);

      aCheckpoints.push([cumA, x]);
      bCheckpoints.push([cumB, x]);

      if (seg.diff.type === "unique_to_b") {
        bMarks.push({ x, width: segWidth, diff: seg.diff });
        aBreaks.push({ x, width: segWidth });
        cumB += seg.bFrames;
      } else if (seg.diff.type === "unique_to_a") {
        aMarks.push({ x, width: segWidth, diff: seg.diff });
        bBreaks.push({ x, width: segWidth });
        cumA += seg.aFrames;
      } else {
        aMarks.push({ x, width: Math.max(MARK_MIN_WIDTH, seg.aFrames * scale), diff: seg.diff });
        bMarks.push({ x, width: Math.max(MARK_MIN_WIDTH, seg.bFrames * scale), diff: seg.diff });
        cumA += seg.aFrames;
        cumB += seg.bFrames;
      }

      x += segWidth;
    }
  }

  function frameToX(frame: number, checkpoints: Array<[number, number]>): number {
    let bestIdx = 0;
    for (let i = 1; i < checkpoints.length; i++) {
      if (checkpoints[i][0] <= frame) bestIdx = i;
      else break;
    }
    const [refFrame, refX] = checkpoints[bestIdx];
    return refX + (frame - refFrame) * scale;
  }

  const chaptersA: ChapterMark[] = data.chapters.theatrical.map((ch) => ({
    x: frameToX(Math.round(ch.start_seconds * data.film.fps), aCheckpoints),
    title: ch.title,
  }));

  const chaptersB: ChapterMark[] = data.chapters.extended.map((ch) => ({
    x: frameToX(Math.round(ch.start_seconds * data.film.fps), bCheckpoints),
    title: ch.title,
  }));

  return { aMarks, bMarks, aBreaks, bBreaks, chaptersA, chaptersB };
}

function buildLinePath(y: number, breaks: BreakRegion[]) {
  const x0 = PAD;
  const x1 = PAD + TIMELINE_WIDTH;
  if (breaks.length === 0) return `M${x0},${y} L${x1},${y}`;

  const sorted = [...breaks].sort((a, b) => a.x - b.x);
  const parts: string[] = [];
  let lastX = x0;

  for (const brk of sorted) {
    const start = Math.max(x0, brk.x + PAD);
    const end = Math.min(x1, brk.x + brk.width + PAD);
    if (start > lastX) {
      parts.push(`M${lastX},${y} L${start},${y}`);
    }
    lastX = end;
  }
  if (lastX < x1) {
    parts.push(`M${lastX},${y} L${x1},${y}`);
  }
  return parts.join(" ");
}

export function Timeline({ data, selected, onSelect }: TimelineProps) {
  const { aMarks, bMarks, aBreaks, bBreaks, chaptersA, chaptersB } = useMemo(
    () => buildLayout(data),
    [data]
  );

  const scrollRef = useRef<HTMLDivElement>(null);

  const selectedX = useMemo(() => {
    if (!selected) return null;
    const mark = [...aMarks, ...bMarks].find((m) => m.diff.index === selected.index);
    if (!mark) return null;
    return mark.x + mark.width / 2 + PAD;
  }, [selected, aMarks, bMarks]);

  // Find the active chapter for the selected difference using frame-based lookup
  const activeChapterA = useMemo(() => {
    if (!selected) return null;
    const frame = selected.theatrical.start_frame;
    const seconds = frame / data.film.fps;
    const chapters = data.chapters.theatrical;
    let best: string | null = null;
    for (let i = 0; i < chapters.length; i++) {
      if (chapters[i].start_seconds <= seconds) {
        best = chapters[i].title;
      } else break;
    }
    return best;
  }, [selected, data]);

  const activeChapterB = useMemo(() => {
    if (!selected) return null;
    const frame = selected.extended.start_frame;
    const seconds = frame / data.film.fps;
    const chapters = data.chapters.extended;
    let best: string | null = null;
    for (let i = 0; i < chapters.length; i++) {
      if (chapters[i].start_seconds <= seconds) {
        best = chapters[i].title;
      } else break;
    }
    return best;
  }, [selected, data]);

  useEffect(() => {
    if (!selected || !scrollRef.current) return;
    const mark = [...aMarks, ...bMarks].find((m) => m.diff.index === selected.index);
    if (!mark) return;
    const container = scrollRef.current;
    const ratio = (mark.x + mark.width / 2 + PAD) / TOTAL_WIDTH;
    const scrollTarget = ratio * container.scrollWidth - container.clientWidth / 2;
    container.scrollTo({ left: scrollTarget, behavior: "smooth" });
  }, [selected, aMarks, bMarks]);

  return (
    <div className="timeline-horizontal" ref={scrollRef}>
      {activeChapterA && selected?.type !== "unique_to_b" && (
        <div className="chapter-label chapter-label-top">{activeChapterA}</div>
      )}
      {activeChapterB && selected?.type !== "unique_to_a" && (
        <div className="chapter-label chapter-label-bottom">{activeChapterB}</div>
      )}
      <svg
        viewBox={`0 0 ${TOTAL_WIDTH} ${SVG_HEIGHT}`}
        className="timeline-svg-h"
        preserveAspectRatio="none"
      >
        {/* Chapter tick marks — all chapters shown as subtle ticks */}
        {chaptersA.map((ch, i) => (
          <line key={`ta-${i}`} x1={ch.x + PAD} y1={CHAPTER_A_Y + 8} x2={ch.x + PAD} y2={LINE_Y_A} stroke="#1a1a1a" strokeWidth="0.5" />
        ))}
        {chaptersB.map((ch, i) => (
          <line key={`tb-${i}`} x1={ch.x + PAD} y1={LINE_Y_B} x2={ch.x + PAD} y2={CHAPTER_B_Y - 8} stroke="#1a1a1a" strokeWidth="0.5" />
        ))}

        {/* Base lines */}
        <path d={buildLinePath(LINE_Y_A, aBreaks)} stroke="#333" strokeWidth="2" fill="none" />
        <path d={buildLinePath(LINE_Y_B, bBreaks)} stroke="#333" strokeWidth="2" fill="none" />

        {/* Theatrical marks */}
        {aMarks.map((m, i) => (
          <rect
            key={`a-${i}`}
            x={m.x + PAD} y={LINE_Y_A - 4}
            width={m.width} height={8}
            rx={1}
            fill={typeColor(m.diff.type)}
            opacity={selected?.index === m.diff.index ? 1 : 0.5}
            className="timeline-mark"
            onClick={() => onSelect(m.diff)}
          />
        ))}

        {/* Extended marks */}
        {bMarks.map((m, i) => (
          <rect
            key={`b-${i}`}
            x={m.x + PAD} y={LINE_Y_B - 4}
            width={m.width} height={8}
            rx={1}
            fill={typeColor(m.diff.type)}
            opacity={selected?.index === m.diff.index ? 1 : 0.5}
            className="timeline-mark"
            onClick={() => onSelect(m.diff)}
          />
        ))}

      </svg>
    </div>
  );
}
