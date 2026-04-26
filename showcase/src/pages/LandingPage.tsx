import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import type { Manifest } from "../types";

const IMAGE_BASE = import.meta.env.PROD
  ? "https://images.gamgee.app"
  : "/data";

const FILM_IMAGES: Record<string, string> = {
  fellowship: `${IMAGE_BASE}/fellowship/${import.meta.env.PROD ? "" : "images/"}cover.png`,
  two_towers: `${IMAGE_BASE}/two_towers/${import.meta.env.PROD ? "" : "images/"}cover.png`,
  return_of_the_king: `${IMAGE_BASE}/return_of_the_king/${import.meta.env.PROD ? "" : "images/"}cover.png`,
};

export function LandingPage() {
  const [manifest, setManifest] = useState<Manifest | null>(null);

  useEffect(() => {
    fetch("/data/manifest.json")
      .then((r) => r.json())
      .then(setManifest);
  }, []);

  if (!manifest) return null;

  return (
    <div className="landing-fullscreen">
      <div className="film-panels">
        {manifest.films.map((film) => (
          <Link key={film.slug} to={`/${film.slug}`} className="film-panel">
            <img
              src={FILM_IMAGES[film.slug]}
              alt=""
              className="film-panel-bg"
            />
            <div className="film-panel-arrow">
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                <path d="M5 12h14M12 5l7 7-7 7" />
              </svg>
            </div>
          </Link>
        ))}
      </div>
    </div>
  );
}
