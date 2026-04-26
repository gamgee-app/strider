const IMAGE_BASE = import.meta.env.PROD
  ? "https://images.gamgee.app"
  : "/data";

const IMAGE_PATH = import.meta.env.PROD
  ? (film: string, edition: string) => `${IMAGE_BASE}/${film}/${edition}`
  : (film: string, edition: string) => `${IMAGE_BASE}/${film}/images/${edition}`;

export function imagePath(
  filmSlug: string,
  edition: "theatrical" | "extended",
  frameIndex: number,
  thumb = false
): string {
  const suffix = thumb ? "_thumb" : "";
  const padded = String(frameIndex).padStart(12, "0");
  return `${IMAGE_PATH(filmSlug, edition)}/frame_${padded}${suffix}.webp`;
}

export function typeLabel(type: string): string {
  switch (type) {
    case "unique_to_b": return "Added in Extended";
    case "unique_to_a": return "Only in Theatrical";
    case "modified": return "Modified";
    case "reordered": return "Reordered";
    default: return type;
  }
}

export function typeColor(type: string): string {
  switch (type) {
    case "unique_to_b": return "#4ade80";
    case "unique_to_a": return "#f87171";
    case "modified": return "#facc15";
    case "reordered": return "#60a5fa";
    default: return "#888";
  }
}

export function formatDuration(seconds: number): string {
  if (seconds < 1) return "<1s";
  if (seconds < 60) return `${Math.round(seconds)}s`;
  const m = Math.floor(seconds / 60);
  const s = Math.round(seconds % 60);
  return s > 0 ? `${m}m ${s}s` : `${m}m`;
}
