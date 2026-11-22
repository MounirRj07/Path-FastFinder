// lib/vizLayers.ts
// Couches MapLibre de la visualisation de Dijkstra (sommets, arêtes, coûts).

import type { LayerSpecification } from "maplibre-gl";
import { COLORS } from "./trace";

export const VIZ_SOURCES = ["viz-edges", "viz-path", "viz-nodes", "viz-labels"] as const;

/** Du dessous vers le dessus. `font` doit exister dans le style de la carte. */
export function vizLayers(font: string[]): LayerSpecification[] {
  return [
    // Arêtes : arbre des plus courts chemins en bleu (fixé) / orange (provisoire)
    {
      id: "viz-edge-lines",
      type: "line",
      source: "viz-edges",
      layout: { "line-cap": "round", "line-join": "round" },
      paint: {
        "line-color": [
          "match", ["get", "st"],
          "tree_settled", COLORS.treeSettled,
          "tree_frontier", COLORS.treeFrontier,
          "closed", COLORS.closed,
          "rejected", COLORS.rejected,
          COLORS.unseen,
        ],
        "line-width": [
          "case",
          ["get", "cur"], 7,
          ["match", ["get", "st"], ["tree_settled", "tree_frontier", "closed"], 4, 2.5],
        ],
        "line-opacity": ["match", ["get", "st"], "unseen", 0.6, 1],
      },
    },
    // Chemin final en vert
    {
      id: "viz-path-line",
      type: "line",
      source: "viz-path",
      layout: { "line-cap": "round", "line-join": "round" },
      paint: { "line-color": COLORS.path, "line-width": 9, "line-opacity": 0.9 },
    },
    // Sommets
    {
      id: "viz-node-circles",
      type: "circle",
      source: "viz-nodes",
      paint: {
        "circle-radius": ["match", ["get", "st"], "current", 11, "settled", 7, "frontier", 6, 4],
        "circle-color": [
          "match", ["get", "st"],
          "current", COLORS.current,
          "settled", COLORS.treeSettled,
          "frontier", COLORS.treeFrontier,
          "#94a3b8",
        ],
        "circle-stroke-width": ["case", ["!=", ["get", "role"], ""], 4, 1.5],
        "circle-stroke-color": [
          "match", ["get", "role"],
          "source", COLORS.source,
          "target", COLORS.target,
          "#ffffff",
        ],
      },
    },
    // Coût de chaque tronçon
    {
      id: "viz-edge-labels",
      type: "symbol",
      source: "viz-labels",
      layout: {
        "text-field": ["get", "label"],
        "text-font": font,
        "text-size": ["case", ["get", "cur"], 15, 12],
        "text-allow-overlap": false,
        "symbol-sort-key": ["get", "prio"],
      },
      paint: {
        "text-color": ["case", ["get", "pen"], "#b91c1c", "#111827"],
        "text-halo-color": "#ffffff",
        "text-halo-width": 2.2,
      },
    },
    // Meilleure distance connue au-dessus de chaque sommet
    {
      id: "viz-node-labels",
      type: "symbol",
      source: "viz-nodes",
      layout: {
        "text-field": ["get", "lbl"],
        "text-font": font,
        "text-size": 12,
        "text-offset": [0, -1.5],
        "text-optional": true,
        "text-allow-overlap": false,
      },
      paint: { "text-color": "#1e3a8a", "text-halo-color": "#ffffff", "text-halo-width": 2 },
    },
  ];
}