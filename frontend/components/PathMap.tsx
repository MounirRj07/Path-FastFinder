"use client";
// components/PathMap.tsx
// À importer avec : dynamic(() => import("@/components/PathMap"), { ssr: false })

import { useCallback, useEffect, useRef, useState } from "react";
import * as maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
maplibregl.setWorkerUrl("/maplibre-gl-worker.mjs");
const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const CENTER: [number, number] = [2.42, 6.37]; // Cotonou : à adapter à ta zone
const BEST_COLOR = "#1d4ed8";
const HIGHLIGHT_COLOR = "#f59e0b";

type Point = [number, number]; // [lng, lat]

type PathResult = {
  id: number;
  distance_m: number;
  duration_s: number;
  coords: Point[];
};

type RouteResponse = {
  paths: PathResult[]; // paths[0] = le plus court
  stats: { nodes_explored: number; compute_ms: number };
};

const fmtDistance = (m: number) =>
  m < 1000 ? `${Math.round(m)} m` : `${(m / 1000).toFixed(1)} km`;

const fmtDuration = (s: number) => {
  const min = Math.round(s / 60);
  if (min < 60) return `${Math.max(min, 1)} min`;
  return `${Math.floor(min / 60)} h ${String(min % 60).padStart(2, "0")} min`;
};

export default function PathMap() {
  const box = useRef<HTMLDivElement>(null);
  const map = useRef<maplibregl.Map | null>(null);
  const startM = useRef<maplibregl.Marker | null>(null);
  const endM = useRef<maplibregl.Marker | null>(null);

  const [ready, setReady] = useState(false);
  const [start, setStart] = useState<Point | null>(null);
  const [end, setEnd] = useState<Point | null>(null);
  const [data, setData] = useState<RouteResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [retry, setRetry] = useState(0);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [hoverId, setHoverId] = useState<number | null>(null);

  // Chemin mis en évidence : survol > sélection
  const highlightId = hoverId ?? selectedId;

  // 1) Création de la carte (une seule fois)
  useEffect(() => {
    if (!box.current) return;

    const m = new maplibregl.Map({
      container: box.current,
      style: "https://tiles.openfreemap.org/styles/liberty",
      center: CENTER,
      zoom: 12,
    });
    map.current = m;
    m.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");

    const addMarker = (
      ref: React.MutableRefObject<maplibregl.Marker | null>,
      color: string,
      p: Point,
      set: (p: Point) => void
    ) => {
      const mk = new maplibregl.Marker({ color, draggable: true }).setLngLat(p).addTo(m);
      mk.on("dragend", () => {
        const ll = mk.getLngLat();
        set([ll.lng, ll.lat]);
      });
      ref.current = mk;
    };

    // 1er clic = départ, 2e clic = arrivée
    m.on("click", (e) => {
      const p: Point = [e.lngLat.lng, e.lngLat.lat];
      if (!startM.current) {
        addMarker(startM, "#16a34a", p, setStart);
        setStart(p);
      } else if (!endM.current) {
        addMarker(endM, "#dc2626", p, setEnd);
        setEnd(p);
      }
    });

    m.on("load", () => {
      m.addSource("paths", {
        type: "geojson",
        data: { type: "FeatureCollection", features: [] },
      });
      // Alternatives en gris
      m.addLayer({
        id: "paths-alt",
        type: "line",
        source: "paths",
        filter: ["==", ["get", "best"], false],
        layout: { "line-cap": "round", "line-join": "round" },
        paint: { "line-color": "#9ca3af", "line-width": 5 },
      });
      // Plus court chemin en couleur
      m.addLayer({
        id: "paths-best",
        type: "line",
        source: "paths",
        filter: ["==", ["get", "best"], true],
        layout: { "line-cap": "round", "line-join": "round" },
        paint: { "line-color": BEST_COLOR, "line-width": 6 },
      });
      // Chemin mis en évidence (par-dessus)
      m.addLayer({
        id: "paths-highlight",
        type: "line",
        source: "paths",
        filter: ["==", ["get", "id"], -1],
        layout: { "line-cap": "round", "line-join": "round" },
        paint: { "line-color": HIGHLIGHT_COLOR, "line-width": 8 },
      });
      // Couche invisible, plus large, pour faciliter le survol
      m.addLayer({
        id: "paths-hit",
        type: "line",
        source: "paths",
        paint: { "line-color": "#000000", "line-width": 18, "line-opacity": 0 },
      });

      m.on("mousemove", "paths-hit", (e) => {
        m.getCanvas().style.cursor = "pointer";
        const id = e.features?.[0]?.properties?.id;
        if (typeof id === "number") setHoverId(id);
      });
      m.on("mouseleave", "paths-hit", () => {
        m.getCanvas().style.cursor = "";
        setHoverId(null);
      });
      m.on("click", "paths-hit", (e) => {
        const id = e.features?.[0]?.properties?.id;
        if (typeof id === "number") setSelectedId(id);
      });

      setReady(true);
    });

    return () => {
      startM.current = null;
      endM.current = null;
      m.remove();
      map.current = null;
    };
  }, []);

  // 2) Appel API à chaque changement de départ / arrivée
  useEffect(() => {
    if (!start || !end) return;
    const ctrl = new AbortController();
    setLoading(true);
    setError(null);

    fetch(`${API}/route`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        start: { lng: start[0], lat: start[1] },
        end: { lng: end[0], lat: end[1] },
        alternatives: 2,
      }),
      signal: ctrl.signal,
    })
      .then((r) => {
        if (!r.ok) throw new Error(`Erreur du serveur (${r.status})`);
        return r.json() as Promise<RouteResponse>;
      })
      .then((d) => {
        if (!d.paths?.length) throw new Error("Aucun chemin trouvé entre ces deux points.");
        setData(d);
        setSelectedId(d.paths[0].id);
      })
      .catch((e) => {
        if (e.name === "AbortError") return;
        setData(null);
        setError(
          e instanceof TypeError
            ? "Impossible de joindre le serveur. Vérifie que l'API est lancée."
            : e.message
        );
      })
      .finally(() => {
        if (!ctrl.signal.aborted) setLoading(false);
      });

    return () => ctrl.abort();
  }, [start, end, retry]);

  // 3) Dessin des chemins + zoom sur le trajet
  useEffect(() => {
    const m = map.current;
    if (!m || !ready) return;
    const src = m.getSource("paths") as maplibregl.GeoJSONSource | undefined;
    if (!src) return;

    const features = (data?.paths ?? []).map((p, i) => ({
      type: "Feature" as const,
      properties: { id: p.id, best: i === 0 },
      geometry: { type: "LineString" as const, coordinates: p.coords },
    }));
    src.setData({ type: "FeatureCollection", features });

    if (data && data.paths[0]?.coords.length) {
      const b = new maplibregl.LngLatBounds();
      data.paths.forEach((p) => p.coords.forEach((c) => b.extend(c)));
      const narrow = window.innerWidth < 768;
      m.fitBounds(b, {
        padding: narrow
          ? { top: 60, left: 40, right: 40, bottom: Math.round(window.innerHeight * 0.4) }
          : { top: 60, bottom: 60, left: 40, right: 380 },
        duration: 600,
      });
    }
  }, [data, ready]);

  // 4) Mise en évidence synchronisée avec la liste
  useEffect(() => {
    const m = map.current;
    if (!m || !ready) return;
    m.setFilter("paths-highlight", ["==", ["get", "id"], highlightId ?? -1]);
  }, [highlightId, ready]);

  const reset = useCallback(() => {
    startM.current?.remove();
    endM.current?.remove();
    startM.current = null;
    endM.current = null;
    setStart(null);
    setEnd(null);
    setData(null);
    setError(null);
    setLoading(false);
    setSelectedId(null);
    setHoverId(null);
  }, []);

  const hint = !start
    ? "Clique sur la carte pour choisir le départ."
    : !end
    ? "Clique pour choisir l'arrivée."
    : null;

  return (
    <div className="pm-root">
      <div ref={box} className="pm-map" />

      <aside className="pm-panel" aria-live="polite">
        <div className="pm-head">
          <h2>Itinéraire</h2>
          {(start || end) && (
            <button className="pm-btn" onClick={reset}>
              Réinitialiser
            </button>
          )}
        </div>

        {hint && <p className="pm-muted">{hint}</p>}

        {loading && (
          <p className="pm-status">
            <span className="pm-spinner" aria-hidden /> Calcul en cours…
          </p>
        )}

        {error && !loading && (
          <div className="pm-error" role="alert">
            <p>{error}</p>
            <button className="pm-btn" onClick={() => setRetry((n) => n + 1)}>
              Réessayer
            </button>
          </div>
        )}

        {data && !loading && !error && (
          <>
            <ul className="pm-list">
              {data.paths.map((p, i) => {
                const active = highlightId === p.id;
                return (
                  <li key={p.id}>
                    <button
                      className={`pm-item ${active ? "is-active" : ""}`}
                      onMouseEnter={() => setHoverId(p.id)}
                      onMouseLeave={() => setHoverId(null)}
                      onFocus={() => setHoverId(p.id)}
                      onBlur={() => setHoverId(null)}
                      onClick={() => setSelectedId(p.id)}
                    >
                      <span
                        className="pm-swatch"
                        style={{ background: i === 0 ? BEST_COLOR : "#9ca3af" }}
                      />
                      <span className="pm-item-main">
                        <strong>{i === 0 ? "Le plus court" : `Alternative ${i}`}</strong>
                        <span>
                          {fmtDistance(p.distance_m)} · {fmtDuration(p.duration_s)}
                        </span>
                      </span>
                    </button>
                  </li>
                );
              })}
            </ul>

            <p className="pm-muted pm-stats">
              Calculé en {data.stats.compute_ms.toFixed(0)} ms,{" "}
              {data.stats.nodes_explored.toLocaleString("fr-FR")} nœuds explorés.
            </p>
          </>
        )}
      </aside>

      <style>{`
        .pm-root { position: relative; width: 100%; height: 100dvh; min-height: 420px; overflow: hidden; }
        .pm-map { position: absolute; inset: 0; }
        .pm-panel {
          position: absolute; z-index: 5; background: #fff; color: #111827;
          font: 15px/1.4 system-ui, sans-serif; padding: 16px; overflow-y: auto;
          box-shadow: 0 2px 16px rgba(0,0,0,.18);
          top: 12px; left: 12px; width: 340px; max-height: calc(100% - 24px); border-radius: 10px;
        }
        .pm-head { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
        .pm-head h2 { margin: 0; font-size: 17px; }
        .pm-muted { margin: 10px 0 0; color: #4b5563; font-size: 14px; }
        .pm-stats { margin-top: 12px; }
        .pm-status { display: flex; align-items: center; gap: 8px; margin: 12px 0 0; }
        .pm-spinner {
          width: 16px; height: 16px; border-radius: 50%;
          border: 2px solid #d1d5db; border-top-color: ${BEST_COLOR};
          animation: pm-spin .8s linear infinite;
        }
        @keyframes pm-spin { to { transform: rotate(360deg); } }
        .pm-error { margin-top: 12px; padding: 10px 12px; border-radius: 8px; background: #fef2f2; color: #991b1b; }
        .pm-error p { margin: 0 0 8px; }
        .pm-list { list-style: none; margin: 12px 0 0; padding: 0; display: grid; gap: 6px; }
        .pm-item {
          width: 100%; display: flex; align-items: center; gap: 10px; text-align: left;
          padding: 10px; border: 1px solid #e5e7eb; border-radius: 8px; background: #fff;
          font: inherit; color: inherit; cursor: pointer;
        }
        .pm-item.is-active { border-color: ${HIGHLIGHT_COLOR}; background: #fffbeb; }
        .pm-item:focus-visible, .pm-btn:focus-visible { outline: 2px solid ${BEST_COLOR}; outline-offset: 2px; }
        .pm-swatch { width: 6px; align-self: stretch; border-radius: 3px; flex: none; }
        .pm-item-main { display: grid; gap: 2px; }
        .pm-item-main span { color: #4b5563; font-size: 14px; }
        .pm-btn {
          padding: 6px 10px; border: 1px solid #d1d5db; border-radius: 6px;
          background: #fff; font: inherit; font-size: 14px; cursor: pointer;
        }
        /* Mobile : le panneau devient un volet en bas */
        @media (max-width: 767px) {
          .pm-panel {
            top: auto; left: 0; right: 0; bottom: 0; width: auto; max-height: 40%;
            border-radius: 14px 14px 0 0; padding: 14px 16px calc(14px + env(safe-area-inset-bottom));
          }
        }
        @media (prefers-reduced-motion: reduce) { .pm-spinner { animation-duration: 2s; } }
      `}</style>
    </div>
  );
}
