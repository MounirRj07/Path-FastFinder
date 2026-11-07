"use client";

import { useEffect, useRef, useState } from "react";
import * as maplibregl from "maplibre-gl";
// @ts-ignore -- import de feuille de style, sans déclaration de types
import "maplibre-gl/dist/maplibre-gl.css";
import { PENALTY_LEVELS, getPenaltyStatus } from "@/lib/types";
import type { NearestEdge, Penalty } from "@/lib/types";

// Même réglage que la carte d'Elnis (PathMap) : le worker est servi depuis public/
maplibregl.setWorkerUrl("/maplibre-gl-worker.mjs");

const STYLE_URL =
  process.env.NEXT_PUBLIC_MAP_STYLE_URL ??
  "https://tiles.openfreemap.org/styles/liberty";

// Abomey-Calavi (voir README) et emprise large autour de l'Atlantique
const CENTER: [number, number] = [2.35, 6.45];
const MAX_BOUNDS: [[number, number], [number, number]] = [
  [1.8, 6.05],
  [2.8, 6.95],
];

// Couleur de chaque tronçon selon son niveau de pénalité
const LEVEL_COLOR = [
  "match",
  ["get", "level"],
  ...PENALTY_LEVELS.flatMap((l) => [l.value, l.color]),
  "#6b7280",
] as unknown as maplibregl.ExpressionSpecification;

function toPenaltyLines(penalties: Penalty[]) {
  return {
    type: "FeatureCollection" as const,
    features: penalties
      .filter((p) => getPenaltyStatus(p) === "active")
      .flatMap((p) =>
        p.geometry.map((coordinates) => ({
          type: "Feature" as const,
          properties: { level: p.level, reason: p.reason },
          geometry: { type: "LineString" as const, coordinates },
        }))
      ),
  };
}

function toSelectionLine(sel: NearestEdge | null) {
  return {
    type: "FeatureCollection" as const,
    features:
      sel && sel.geometry.length >= 2
        ? [
            {
              type: "Feature" as const,
              properties: {},
              geometry: {
                type: "LineString" as const,
                coordinates: sel.geometry,
              },
            },
          ]
        : [],
  };
}

interface Props {
  /** Pénalités à afficher (seules les actives sont dessinées) */
  penalties: Penalty[];
  /** Tronçon ou rue actuellement sélectionné (surligné en bleu) */
  selection: NearestEdge | null;
  /** Appelé à chaque clic sur la carte */
  onMapClick: (lat: number, lon: number) => void;
}

export default function AdminMap({ penalties, selection, onMapClick }: Props) {
  const container = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const clickRef = useRef(onMapClick);
  const loadedRef = useRef(false);
  const [ready, setReady] = useState(false);
  const [mapError, setMapError] = useState<string | null>(null);

  // Garde toujours la dernière version du callback sans recréer la carte
  useEffect(() => {
    clickRef.current = onMapClick;
  });

  // Création de la carte (une seule fois)
  useEffect(() => {
    if (!container.current) return;

    const map = new maplibregl.Map({
      container: container.current,
      style: STYLE_URL,
      center: CENTER,
      zoom: 10,
      maxBounds: MAX_BOUNDS,
    });
    mapRef.current = map;
    map.addControl(
      new maplibregl.NavigationControl({ showCompass: false }),
      "top-right"
    );
    map.getCanvas().style.cursor = "crosshair";

    map.on("load", () => {
      map.addSource("penalties", { type: "geojson", data: toPenaltyLines([]) });
      map.addSource("selection", { type: "geojson", data: toSelectionLine(null) });
      map.addLayer({
        id: "penalties-line",
        type: "line",
        source: "penalties",
        layout: { "line-cap": "round", "line-join": "round" },
        paint: { "line-color": LEVEL_COLOR, "line-width": 6, "line-opacity": 0.9 },
      });
      map.addLayer({
        id: "selection-line",
        type: "line",
        source: "selection",
        layout: { "line-cap": "round", "line-join": "round" },
        paint: { "line-color": "#2563eb", "line-width": 9, "line-opacity": 0.85 },
      });
      loadedRef.current = true;
      setReady(true);
    });

    map.on("click", (e) => clickRef.current(e.lngLat.lat, e.lngLat.lng));

    map.on("error", () => {
      if (!loadedRef.current) {
        setMapError("Fond de carte indisponible. Vérifiez la connexion internet.");
      }
    });

    return () => {
      map.remove();
      mapRef.current = null;
      loadedRef.current = false;
    };
  }, []);

  // Pénalités actives, colorées par niveau
  useEffect(() => {
    if (!ready) return;
    const src = mapRef.current?.getSource("penalties") as
      | maplibregl.GeoJSONSource
      | undefined;
    src?.setData(toPenaltyLines(penalties));
  }, [penalties, ready]);

  // Tronçon ou rue sélectionné
  useEffect(() => {
    if (!ready) return;
    const src = mapRef.current?.getSource("selection") as
      | maplibregl.GeoJSONSource
      | undefined;
    src?.setData(toSelectionLine(selection));
  }, [selection, ready]);

  return (
    <div className="relative h-[420px] w-full overflow-hidden rounded-xl border border-gray-300">
      <div ref={container} className="h-full w-full" />

      {mapError && (
        <p
          role="alert"
          className="absolute inset-x-0 top-0 bg-red-600 p-2 text-center text-sm text-white"
        >
          {mapError}
        </p>
      )}

      <ul className="absolute bottom-2 left-2 space-y-1 rounded-md bg-white/90 p-2 text-xs text-black">
        {PENALTY_LEVELS.map((l) => (
          <li key={l.value} className="flex items-center gap-2">
            <span
              className="inline-block h-1.5 w-5 rounded"
              style={{ backgroundColor: l.color }}
            />
            {l.label}
          </li>
        ))}
        <li className="flex items-center gap-2">
          <span className="inline-block h-1.5 w-5 rounded bg-blue-600" />
          Sélection
        </li>
      </ul>
    </div>
  );
}
