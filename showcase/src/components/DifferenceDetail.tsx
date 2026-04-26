import type { Difference } from "../types";
import { imagePath, typeLabel, typeColor, formatDuration } from "../utils";

interface Props {
  diff: Difference;
  filmSlug: string;
}

export function DifferenceDetail({ diff, filmSlug }: Props) {
  const t = diff.theatrical;
  const e = diff.extended;
  const tImages = diff.images.theatrical;
  const eImages = diff.images.extended;
  const tSamples = tImages.slice(1);
  const eSamples = eImages.slice(1);

  return (
    <div>
      <div className="detail-header">
        <span className="type-badge" style={{
          backgroundColor: typeColor(diff.type) + "20",
          color: typeColor(diff.type),
        }}>
          {typeLabel(diff.type)}
        </span>
        <span style={{ color: "#555", fontSize: "0.85rem" }}>
          #{diff.index}
        </span>
      </div>

      <div className="detail-columns">
        {/* Left: Theatrical */}
        <div className="detail-col">
          <div className="detail-col-header">
            <dt>Theatrical</dt>
            <dd>
              {t.start_time}
              {t.duration_seconds > 0 && ` \u2013 ${t.end_time}`}
              {t.duration_seconds > 0 && (
                <span style={{ color: "#666" }}>
                  {" "}({formatDuration(t.duration_seconds)})
                </span>
              )}
            </dd>
            <dd className="chapter">{t.chapter}</dd>
          </div>

          {tImages.length > 0 ? (
            <img
              className="detail-hero"
              src={imagePath(filmSlug, "theatrical", tImages[0])}
              loading="lazy"
            />
          ) : (
            <div className="detail-hero-empty" />
          )}
        </div>

        {/* Right: Extended */}
        <div className="detail-col">
          <div className="detail-col-header">
            <dt>Extended</dt>
            <dd>
              {e.start_time}
              {e.duration_seconds > 0 && ` \u2013 ${e.end_time}`}
              {e.duration_seconds > 0 && (
                <span style={{ color: "#666" }}>
                  {" "}({formatDuration(e.duration_seconds)})
                </span>
              )}
            </dd>
            <dd className="chapter">{e.chapter}</dd>
          </div>

          {eImages.length > 0 ? (
            <img
              className="detail-hero"
              src={imagePath(filmSlug, "extended", eImages[0])}
              loading="lazy"
            />
          ) : (
            <div className="detail-hero-empty" />
          )}
        </div>
      </div>

      {/* Sample thumbnails — still left/right columns */}
      {(tSamples.length > 0 || eSamples.length > 0) && (
        <div className="detail-columns">
          <div className="detail-col">
            <div className="samples-grid">
              {tSamples.map((frame) => (
                <img
                  key={frame}
                  src={imagePath(filmSlug, "theatrical", frame, true)}
                  loading="lazy"
                />
              ))}
            </div>
          </div>
          <div className="detail-col">
            <div className="samples-grid">
              {eSamples.map((frame) => (
                <img
                  key={frame}
                  src={imagePath(filmSlug, "extended", frame, true)}
                  loading="lazy"
                />
              ))}
            </div>
          </div>
        </div>
      )}

      {diff.reordered_info && (
        <div className="reorder-note">
          This content also appears at {diff.reordered_info.time_range} in the
          extended edition ({diff.reordered_info.matching_frames} matching frames)
        </div>
      )}
    </div>
  );
}
