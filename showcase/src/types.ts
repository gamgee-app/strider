export interface FilmStats {
  added: number;
  removed: number;
  modified: number;
  reordered: number;
  extra_minutes: number;
}

export interface FilmSummary {
  slug: string;
  title: string;
  year: number;
  total_differences: number;
  theatrical_frames: number;
  extended_frames: number;
  hero_frame: number | null;
  stats: FilmStats;
}

export interface Manifest {
  films: FilmSummary[];
}

export interface Chapter {
  start_seconds: number;
  title: string;
}

export interface EditionInfo {
  start_frame: number;
  end_frame: number;
  start_time: string;
  end_time: string;
  duration_seconds: number;
  chapter: string;
}

export interface ReorderedInfo {
  time_range: string;
  matching_frames: number;
}

export interface Difference {
  index: number;
  type: "unique_to_a" | "unique_to_b" | "modified" | "reordered";
  theatrical: EditionInfo;
  extended: EditionInfo;
  duration_difference_seconds: number;
  images: {
    theatrical: number[];
    extended: number[];
  };
  reordered_info: ReorderedInfo | null;
}

export interface FilmData {
  film: {
    slug: string;
    title: string;
    year: number;
    fps: number;
    theatrical_frames: number;
    extended_frames: number;
  };
  chapters: {
    theatrical: Chapter[];
    extended: Chapter[];
  };
  differences: Difference[];
}
