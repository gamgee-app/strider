import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { Timeline } from "../components/Timeline";
import { DifferenceDetail } from "../components/DifferenceDetail";
import type { FilmData, Difference } from "../types";

export function FilmPage() {
  const { slug } = useParams<{ slug: string }>();
  const [data, setData] = useState<FilmData | null>(null);
  const [selected, setSelected] = useState<Difference | null>(null);
  const pageRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setData(null);
    setSelected(null);
    fetch(`/data/${slug}/data.json`)
      .then((r) => r.json())
      .then((d: FilmData) => {
        setData(d);
        if (d.differences.length > 0) setSelected(d.differences[0]);
      });
  }, [slug]);

  const navigate = useCallback(
    (direction: 1 | -1) => {
      if (!data || !selected) return;
      const idx = data.differences.findIndex((d) => d.index === selected.index);
      const next = idx + direction;
      if (next >= 0 && next < data.differences.length) {
        setSelected(data.differences[next]);
      }
    },
    [data, selected]
  );

  useEffect(() => {
    const el = pageRef.current;
    if (!el) return;

    let cooldown = false;
    const onWheel = (e: WheelEvent) => {
      e.preventDefault();
      if (cooldown) return;
      cooldown = true;
      setTimeout(() => (cooldown = false), 300);

      if (e.deltaY > 0) navigate(1);
      else if (e.deltaY < 0) navigate(-1);
    };

    el.addEventListener("wheel", onWheel, { passive: false });
    return () => el.removeEventListener("wheel", onWheel);
  }, [navigate]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "ArrowDown" || e.key === "ArrowRight") {
        e.preventDefault();
        navigate(1);
      } else if (e.key === "ArrowUp" || e.key === "ArrowLeft") {
        e.preventDefault();
        navigate(-1);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [navigate]);

  if (!data) return null;

  return (
    <div className="film-page" data-film={slug} ref={pageRef}>
      <div className="film-header">
        <Link to="/">&larr;</Link>
        <h1>{data.film.title}</h1>
        <span className="diff-count">
          {selected
            ? `${data.differences.findIndex((d) => d.index === selected.index) + 1} / ${data.differences.length}`
            : `${data.differences.length} differences`}
        </span>
      </div>

      <div className="detail-panel">
        {selected ? (
          <DifferenceDetail diff={selected} filmSlug={data.film.slug} />
        ) : (
          <div className="detail-empty">Select a difference</div>
        )}
      </div>

      <Timeline data={data} selected={selected} onSelect={setSelected} />
    </div>
  );
}
