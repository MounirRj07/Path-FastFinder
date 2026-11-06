"""
graph.py — Chargement du graphe routier en mémoire et accès à ses données.

Le graphe est chargé UNE SEULE FOIS au démarrage du serveur (voir main.py),
puis partagé en lecture seule par toutes les requêtes.

Responsable : Mounir
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

SUPPORTED_FORMAT_VERSION = 1

_ARRAYS = (
    "offsets", "sources", "targets", "lengths", "speeds", "way_ids",
    "name_ids", "highway_ids", "node_coords", "node_osmids",
    "geom_offsets", "geom_coords",
)


class GraphFormatError(Exception):
    """Les fichiers du graphe sont absents, incomplets ou incohérents."""


@dataclass(frozen=True)
class Graph:
    # --- Structure CSR (utilisée par Dijkstra) ---
    offsets: np.ndarray       # (N+1,) int64 : arêtes sortant de u = offsets[u] .. offsets[u+1]-1
    targets: np.ndarray       # (E,)   int32 : nœud d'arrivée de chaque arête
    lengths: np.ndarray       # (E,)   float64 : longueur en mètres
    # --- Données complémentaires ---
    sources: np.ndarray       # (E,)   int32 : nœud de départ de chaque arête
    speeds: np.ndarray        # (E,)   float32 : vitesse estimée en km/h
    way_ids: np.ndarray       # (E,)   int64 : id OSM de la rue (-1 si inconnu)
    name_ids: np.ndarray      # (E,)   int32 : indice dans `names`
    highway_ids: np.ndarray   # (E,)   int16 : indice dans `highways`
    node_coords: np.ndarray   # (N,2)  float64 : (lon, lat)
    node_osmids: np.ndarray   # (N,)   int64 : id OSM d'origine de chaque nœud
    geom_offsets: np.ndarray  # (E+1,) int64 : points de l'arête e = geom_coords[geom_offsets[e]:geom_offsets[e+1]]
    geom_coords: np.ndarray   # (P,2)  float64 : (lon, lat)
    names: list[str]
    highways: list[str]
    meta: dict
    _way_index: dict = field(repr=False)

    # ------------------------------------------------------------------
    @classmethod
    def load(cls, path: str | Path) -> "Graph":
        path = Path(path)
        if not path.is_dir():
            raise GraphFormatError(f"Dossier du graphe introuvable : {path}. "
                                   "Lancer preprocessing/build_graph.py ou télécharger la release.")
        try:
            arrays = {name: np.load(path / f"{name}.npy") for name in _ARRAYS}
            names = json.loads((path / "names.json").read_text(encoding="utf-8"))
            highways = json.loads((path / "highways.json").read_text(encoding="utf-8"))
            meta = json.loads((path / "meta.json").read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise GraphFormatError(f"Fichier manquant : {exc.filename}") from exc

        if meta.get("format_version") != SUPPORTED_FORMAT_VERSION:
            raise GraphFormatError(f"Version de format {meta.get('format_version')} non supportée")

        # Index rue -> arêtes, pour pénaliser « toute la rue » d'un coup
        way_index: dict[int, np.ndarray] = {}
        way_ids = arrays["way_ids"]
        order = np.argsort(way_ids, kind="stable")
        uniq, starts = np.unique(way_ids[order], return_index=True)
        bounds = np.append(starts, len(order))
        for k, way in enumerate(uniq.tolist()):
            if way >= 0:
                way_index[way] = np.sort(order[bounds[k]:bounds[k + 1]])

        graph = cls(**arrays, names=names, highways=highways, meta=meta, _way_index=way_index)
        graph._validate()
        return graph

    def _validate(self) -> None:
        n, e = self.n_nodes, self.n_edges
        checks = {
            "offsets doit avoir N+1 éléments": len(self.offsets) == n + 1,
            "offsets[0] doit valoir 0": self.offsets[0] == 0,
            "offsets[-1] doit valoir E": self.offsets[-1] == e,
            "offsets doit être croissant": bool(np.all(np.diff(self.offsets) >= 0)),
            "tableaux d'arêtes de longueur E": all(
                len(a) == e for a in (self.sources, self.lengths, self.speeds, self.way_ids,
                                      self.name_ids, self.highway_ids)),
            "targets dans [0, N)": e == 0 or (self.targets.min() >= 0 and self.targets.max() < n),
            "longueurs positives": e == 0 or self.lengths.min() > 0,
            "vitesses positives": e == 0 or self.speeds.min() > 0,
            "geom_offsets de longueur E+1": len(self.geom_offsets) == e + 1,
            "chaque arête a au moins 2 points": bool(np.all(np.diff(self.geom_offsets) >= 2)),
            "sources cohérent avec offsets": bool(np.array_equal(
                self.sources, np.repeat(np.arange(n, dtype=np.int32), np.diff(self.offsets)))),
        }
        errors = [msg for msg, ok in checks.items() if not ok]
        if errors:
            raise GraphFormatError("Graphe invalide : " + " ; ".join(errors))

    # ------------------------------------------------------------------
    @property
    def n_nodes(self) -> int:
        return len(self.node_osmids)

    @property
    def n_edges(self) -> int:
        return len(self.targets)

    def out_edges(self, u: int) -> range:
        """Identifiants des arêtes qui sortent du nœud u."""
        return range(int(self.offsets[u]), int(self.offsets[u + 1]))

    def find_edge(self, u: int, v: int) -> int | None:
        """Arête u -> v, ou None. Recherche dichotomique (targets est trié par nœud)."""
        start, end = int(self.offsets[u]), int(self.offsets[u + 1])
        k = start + int(np.searchsorted(self.targets[start:end], v))
        return k if k < end and self.targets[k] == v else None

    def reverse_edge(self, e: int) -> int | None:
        """Arête dans l'autre sens (v -> u), ou None si la route est à sens unique."""
        return self.find_edge(int(self.targets[e]), int(self.sources[e]))

    def edges_of_way(self, way_id: int) -> np.ndarray:
        """Toutes les arêtes (dans les deux sens) appartenant à une rue OSM."""
        return self._way_index.get(int(way_id), np.empty(0, dtype=np.int64))

    # ------------------------------------------------------------------
    def edge_name(self, e: int) -> str:
        return self.names[self.name_ids[e]]

    def edge_highway(self, e: int) -> str:
        return self.highways[self.highway_ids[e]]

    def edge_duration_s(self, e: int) -> float:
        return float(self.lengths[e] / (self.speeds[e] / 3.6))

    def edge_geometry(self, e: int) -> np.ndarray:
        """Tracé de l'arête : tableau (k, 2) de (lon, lat), orienté de la source vers la cible."""
        return self.geom_coords[self.geom_offsets[e]:self.geom_offsets[e + 1]]

    def path_geometry(self, edge_ids) -> list[list[float]]:
        """Tracé continu d'un chemin (liste d'arêtes consécutives), sans doublons aux jonctions."""
        edge_ids = list(edge_ids)
        if not edge_ids:
            return []
        parts = [self.edge_geometry(edge_ids[0])]
        parts += [self.edge_geometry(e)[1:] for e in edge_ids[1:]]
        return np.concatenate(parts).tolist()

    def path_stats(self, edge_ids) -> tuple[float, float]:
        """(distance en m, durée en s) d'un chemin."""
        idx = np.asarray(list(edge_ids), dtype=np.int64)
        if idx.size == 0:
            return 0.0, 0.0
        return float(self.lengths[idx].sum()), float((self.lengths[idx] / (self.speeds[idx] / 3.6)).sum())
