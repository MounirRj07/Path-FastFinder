"use client";
// components/AlgoViz.tsx
// Visualisation pas à pas de Dijkstra : sommets (carrefours), arêtes (tronçons),
// coût de chaque tronçon, et choix du sommet à chaque étape.
// Utilisé par PathMap.tsx (bouton « Voir l'algorithme »).

import { useEffect, useMemo, useState } from "react";
import * as maplibregl from "maplibre-gl";
import {
  COLORS,
  edgesGeoJSON,
  labelsGeoJSON,
  narrate,
  nodesGeoJSON,
  pathGeoJSON,
  prepareTrace,
  stateAt,
  type FC,
  type Point,
  type TraceData,
} from "../lib/trace";
import { VIZ_SOURCES, vizLayers } from "../lib/vizLayers";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

const EMPTY: FC = { type: "FeatureCollection", features: [] };
const ROUTE_LAYERS = ["paths-alt", "paths-best", "paths-highlight", "paths-hit"];
const SPEEDS = [1, 3, 10, 30]; // étapes par seconde

type Props = {
  map: maplibregl.Map;
  start: Point; // [lng, lat]
  end: Point; // [lng, lat]
  onClose: () => void;
};

/** Reprend une police déjà utilisée par le style de la carte (sinon les textes ne s'affichent pas). */
function findFont(map: maplibregl.Map): string[] {
  const layers = map.getStyle()?.layers ?? [];
  for (const l of layers) {
    const f = (l as { layout?: Record<string, unknown> }).layout?.["text-font"];
    if (Array.isArray(f) && f.every((x) => typeof x === "string")) return f as string[];
  }
  return ["Noto Sans Regular"];
}

export default function AlgoViz({ map, start, end, onClose }: Props) {
  const [data, setData] = useState<TraceData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [k, setK] = useState(0); // nombre d'étapes jouées
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(3);

  // 1) Chargement de la trace depuis l'API
  useEffect(() => {
    const ctrl = new AbortController();
    setLoading(true);
    setError(null);
    setData(null);
    setK(0);
    setPlaying(false);

    const params = new URLSearchParams({
      from_lat: String(start[1]),
      from_lon: String(start[0]),
      to_lat: String(end[1]),
      to_lon: String(end[0]),
    });
    fetch(`${API}/route/trace?${params}`, { signal: ctrl.signal })
      .then(async (r) => {
        if (!r.ok) {
          let detail = "";
          try {
            const b = await r.json();
            if (typeof b?.detail === "string") detail = b.detail;
          } catch {
            /* corps non JSON */
          }
          throw new Error(detail || `Erreur du serveur (${r.status})`);
        }
        return r.json() as Promise<TraceData>;
      })
      .then((d) => setData(d))
      .catch((e) => {
        if (e.name === "AbortError") return;
        setError(
          e instanceof TypeError ? "Impossible de joindre le serveur. Réessayez dans une minute." : e.message
        );
      })
      .finally(() => {
        if (!ctrl.signal.aborted) setLoading(false);
      });
    return () => ctrl.abort();
  }, [start[0], start[1], end[0], end[1]]); // eslint-disable-line react-hooks/exhaustive-deps

  // 2) Création des couches sur la carte (retirées à la fermeture)
  useEffect(() => {
    const font = findFont(map);
    const hidden = ROUTE_LAYERS.filter((id) => map.getLayer(id));
    hidden.forEach((id) => map.setLayoutProperty(id, "visibility", "none"));

    VIZ_SOURCES.forEach((id) => map.addSource(id, { type: "geojson", data: EMPTY }));

    vizLayers(font).forEach((layer) => map.addLayer(layer));

    return () => {
      try {
        vizLayers([]).reverse().forEach((l) => map.getLayer(l.id) && map.removeLayer(l.id));
        VIZ_SOURCES.forEach((id) => map.getSource(id) && map.removeSource(id));
        ROUTE_LAYERS.filter((id) => map.getLayer(id)).forEach((id) =>
          map.setLayoutProperty(id, "visibility", "visible")
        );
      } catch {
        /* la carte a déjà été détruite (fermeture de la page) */
      }
    };
  }, [map]);

  // 3) Calculs dérivés de la trace et de l'étape
  const prep = useMemo(() => (data ? prepareTrace(data) : null), [data]);
  const view = useMemo(() => (data ? stateAt(data, k) : null), [data, k]);
  const text = useMemo(() => (data && prep ? narrate(data, prep, k) : null), [data, prep, k]);
  const total = data?.steps.length ?? 0;

  // 4) Mise à jour des couches à chaque étape
  useEffect(() => {
    if (!data || !prep || !view) return;
    const set = (id: string, fc: FC) =>
      (map.getSource(id) as maplibregl.GeoJSONSource | undefined)?.setData(fc as never);
    set("viz-edges", edgesGeoJSON(prep, view));
    set("viz-labels", labelsGeoJSON(prep, view));
    set("viz-nodes", nodesGeoJSON(data, prep, view));
    set("viz-path", pathGeoJSON(data, prep, k));
  }, [map, data, prep, view, k]);

  // 5) Cadrage de la carte sur la zone explorée
  useEffect(() => {
    if (!data || data.nodes.length === 0) return;
    const b = new maplibregl.LngLatBounds();
    data.nodes.forEach((n) => b.extend([n.lon, n.lat]));
    const narrow = window.innerWidth < 768;
    map.fitBounds(b, {
          padding: narrow
        ? { top: 60, bottom: Math.round(window.innerHeight * 0.55) + 20, left: 30, right: 30 }
        : { top: 60, bottom: 60, left: 380, right: 60 },
      duration: 600,
      maxZoom: 19,
    });
  }, [map, data]);

  // 6) Lecture automatique
  useEffect(() => {
    if (!playing || total === 0) return;
    const id = setInterval(() => setK((p) => Math.min(p + 1, total)), 1000 / speed);
    return () => clearInterval(id);
  }, [playing, speed, total]);
  useEffect(() => {
    if (total > 0 && k >= total) setPlaying(false);
  }, [k, total]);

  const goTo = (n: number) => setK(Math.max(0, Math.min(total, n)));
  const togglePlay = () => {
    if (k >= total) setK(0); // relire depuis le début
    setPlaying((p) => !p);
  };

  return (
    <section className="av-panel" aria-label="Visualisation de l'algorithme de Dijkstra">
      <div className="av-head">
        <h3>Dijkstra pas à pas</h3>
        <button className="av-btn" onClick={onClose} aria-label="Fermer la visualisation">
          ✕
        </button>
      </div>

      {loading && <p className="av-muted">Calcul de la trace…</p>}

      {error && !loading && <p className="av-error">{error}</p>}

      {data && text && (
        <>
          <div className="av-controls">
            <button className="av-btn" onClick={() => goTo(0)} aria-label="Retour au début">⏮</button>
            <button className="av-btn" onClick={() => goTo(k - 1)} aria-label="Étape précédente">◀</button>
            <button className="av-btn av-play" onClick={togglePlay}>
              {playing ? "⏸ Pause" : k >= total ? "↻ Rejouer" : "▶ Lecture"}
            </button>
            <button className="av-btn" onClick={() => goTo(k + 1)} aria-label="Étape suivante">▶|</button>
            <button className="av-btn" onClick={() => goTo(total)} aria-label="Aller à la fin">⏭</button>
            <select
              className="av-btn"
              value={speed}
              onChange={(e) => setSpeed(Number(e.target.value))}
              aria-label="Vitesse de lecture"
            >
              {SPEEDS.map((s) => (
                <option key={s} value={s}>
                  {s} étape{s > 1 ? "s" : ""}/s
                </option>
              ))}
            </select>
          </div>

          <input
            className="av-range"
            type="range"
            min={0}
            max={total}
            value={k}
            onChange={(e) => setK(Number(e.target.value))}
            aria-label="Position dans l'algorithme"
          />

          <div className="av-text" aria-live="polite">
            <strong>{text.title}</strong>
            {text.lines.map((l, i) => (
              <p key={i}>{l}</p>
            ))}
          </div>

          <ul className="av-legend">
            <li><i style={{ background: COLORS.treeSettled }} />fixé (définitif)</li>
            <li><i style={{ background: COLORS.treeFrontier }} />découvert (provisoire)</li>
            <li><i style={{ background: COLORS.current }} />sommet choisi</li>
            <li><i style={{ background: COLORS.rejected }} />arête écartée</li>
            <li><i style={{ background: COLORS.closed }} />route fermée</li>
            <li><i style={{ background: COLORS.path }} />chemin final</li>
          </ul>
          <p className="av-muted">
            Nombre sur un sommet : meilleur coût connu depuis le départ. Nombre sur un tronçon : son
            coût (longueur × pénalité, en rouge si pénalisé). {data.stats.nodes_explored} sommets et{" "}
            {data.stats.edges_examined} arêtes examinés.
          </p>
        </>
      )}

      <style>{`
        .av-panel {
          margin-top: 14px; padding-top: 14px; border-top: 1px solid #e5e7eb;
          color: #111827; font: 14px/1.4 system-ui, sans-serif;
        }
        .av-head { display: flex; align-items: center; justify-content: space-between; }
        .av-head h3 { margin: 0; font-size: 16px; }
        .av-controls { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 8px; }
        .av-btn {
          padding: 5px 9px; border: 1px solid #d1d5db; border-radius: 6px;
          background: #fff; font: inherit; cursor: pointer;
        }
        .av-play { background: #1d4ed8; border-color: #1d4ed8; color: #fff; min-width: 96px; }
        .av-btn:focus-visible { outline: 2px solid #1d4ed8; outline-offset: 2px; }
        .av-range { width: 100%; margin: 8px 0 2px; }
        .av-text { margin-top: 6px; padding: 8px 10px; background: #f3f4f6; border-radius: 8px; }
        .av-text p { margin: 4px 0 0; color: #374151; }
        .av-muted { margin: 8px 0 0; color: #4b5563; font-size: 13px; }
        .av-error { margin: 8px 0 0; padding: 8px 10px; background: #fef2f2; color: #991b1b; border-radius: 8px; }
        .av-legend { display: flex; flex-wrap: wrap; gap: 4px 14px; margin: 8px 0 0; padding: 0; list-style: none; font-size: 13px; }
        .av-legend li { display: flex; align-items: center; gap: 5px; }
        .av-legend i { width: 14px; height: 6px; border-radius: 3px; display: inline-block; }
       
      `}</style>
    </section>
  );
}