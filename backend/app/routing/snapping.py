"""
snapping.py — Accroche d'un point cliqué au réseau routier.

  - nearest_node : point -> carrefour le plus proche (départ / arrivée de Dijkstra)
  - nearest_edge : point -> tronçon le plus proche (sélection d'une route par l'admin)
  - select_road  : point -> toutes les arêtes à pénaliser (les deux sens, ou toute la rue)

Les distances sont calculées en mètres après une projection locale
(équirectangulaire), largement assez précise à l'échelle d'un département.

Responsable : Mounir
"""

from __future__ import annotations

import math

import numpy as np
from scipy.spatial import cKDTree

from .graph import Graph

EARTH_RADIUS_M = 6_371_008.8
MAX_SNAP_DISTANCE_M = 500.0     # au-delà : point considéré hors zone
MAX_SUBSEGMENT_M = 25.0         # découpage des longs segments pour l'index


class OutOfZoneError(Exception):
    """Le point est trop loin de toute route du graphe."""

    def __init__(self, distance_m: float):
        super().__init__(f"Aucune route à moins de {MAX_SNAP_DISTANCE_M:.0f} m "
                         f"(route la plus proche à {distance_m:.0f} m)")
        self.distance_m = distance_m


class Snapper:
    def __init__(self, graph: Graph, max_distance_m: float = MAX_SNAP_DISTANCE_M):
        self.graph = graph
        self.max_distance_m = max_distance_m

        # Latitude de référence pour la projection : centre de la zone
        self._lat0 = math.radians(float(np.mean(graph.node_coords[:, 1])))
        self._kx = EARTH_RADIUS_M * math.cos(self._lat0) * math.pi / 180.0
        self._ky = EARTH_RADIUS_M * math.pi / 180.0

        # --- Index des nœuds ---
        self._node_tree = cKDTree(self._project(graph.node_coords))

        # --- Index des segments ---
        # Chaque arête est une polyligne ; on indexe tous ses segments.
        pts = self._project(graph.geom_coords)
        go = graph.geom_offsets
        n_pts_per_edge = np.diff(go)
        # Un segment relie le point i au point i+1, sauf entre deux arêtes.
        is_last_point = np.zeros(len(pts), dtype=bool)
        is_last_point[go[1:] - 1] = True
        seg_start = np.flatnonzero(~is_last_point)
        seg_edge = np.repeat(np.arange(graph.n_edges), n_pts_per_edge - 1)
        a, b = pts[seg_start], pts[seg_start + 1]

        # Les longs segments (route droite de 2 km) sont découpés en morceaux
        # de 25 m : sinon le milieu du segment serait loin du clic et l'index
        # KD-tree pourrait ne pas le proposer.
        seg_len = np.linalg.norm(b - a, axis=1)
        n_sub = np.maximum(1, np.ceil(seg_len / MAX_SUBSEGMENT_M).astype(np.int64))
        rep = np.repeat(np.arange(len(a)), n_sub)
        k = np.arange(len(rep)) - np.repeat(np.cumsum(n_sub) - n_sub, n_sub)
        t0 = (k / n_sub[rep])[:, None]
        t1 = ((k + 1) / n_sub[rep])[:, None]
        d = (b - a)[rep]
        self._seg_a = a[rep] + t0 * d
        self._seg_b = a[rep] + t1 * d
        self._seg_edge = seg_edge[rep]
        self._seg_tree = cKDTree((self._seg_a + self._seg_b) / 2.0)

    # ------------------------------------------------------------------
    def _project(self, lonlat: np.ndarray) -> np.ndarray:
        lonlat = np.asarray(lonlat, dtype=np.float64).reshape(-1, 2)
        return np.column_stack((lonlat[:, 0] * self._kx, lonlat[:, 1] * self._ky))

    def _check(self, distance_m: float) -> None:
        if distance_m > self.max_distance_m:
            raise OutOfZoneError(distance_m)

    # ------------------------------------------------------------------
    def nearest_node(self, lat: float, lon: float) -> tuple[int, float]:
        """(identifiant du nœud, distance en m) du carrefour le plus proche."""
        dist, idx = self._node_tree.query(self._project([lon, lat])[0])
        self._check(float(dist))
        return int(idx), float(dist)

    def nearest_edge(self, lat: float, lon: float, k: int = 32) -> tuple[int, float]:
        """(identifiant de l'arête, distance en m) du tronçon le plus proche du point."""
        p = self._project([lon, lat])[0]
        k = min(k, len(self._seg_edge))
        _, idx = self._seg_tree.query(p, k=k)
        idx = np.atleast_1d(idx)

        # Distance exacte point -> segment pour les k candidats
        a, b = self._seg_a[idx], self._seg_b[idx]
        ab = b - a
        denom = np.einsum("ij,ij->i", ab, ab)
        t = np.where(denom > 0, np.einsum("ij,ij->i", p - a, ab) / np.where(denom > 0, denom, 1), 0.0)
        t = np.clip(t, 0.0, 1.0)
        dist = np.linalg.norm(a + t[:, None] * ab - p, axis=1)

        best = int(np.argmin(dist))
        self._check(float(dist[best]))
        return int(self._seg_edge[idx[best]]), float(dist[best])

    def select_road(self, lat: float, lon: float, whole_way: bool = False) -> list[int]:
        """
        Arêtes à pénaliser quand l'admin clique sur une route.
        Une route à double sens = 2 arêtes (u->v et v->u) : on renvoie toujours les deux.
        Avec whole_way=True : toutes les arêtes de la rue OSM.
        """
        e, _ = self.nearest_edge(lat, lon)
        if whole_way and self.graph.way_ids[e] >= 0:
            return self.graph.edges_of_way(int(self.graph.way_ids[e])).tolist()
        edges = [e]
        rev = self.graph.reverse_edge(e)
        if rev is not None:
            edges.append(rev)
        return sorted(edges)
