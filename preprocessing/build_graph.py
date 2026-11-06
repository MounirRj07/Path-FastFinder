"""
build_graph.py — Transforme le réseau routier OpenStreetMap du département de
l'Atlantique (Bénin) en graphe orienté au format CSR, prêt pour Dijkstra.

Utilisation :
    python build_graph.py                      # génère ../data/graph/
    python build_graph.py --geojson            # + edges.geojson (pour QGIS / débogage)
    python build_graph.py --place "Abomey-Calavi, Bénin" --out ../data/graph_test

Responsable : Mounir
"""

from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

# Vitesses par défaut (km/h) selon le type de route OSM, quand la balise
# maxspeed est absente (cas le plus fréquent dans la zone).
DEFAULT_SPEEDS_KPH = {
    "motorway": 90, "motorway_link": 50,
    "trunk": 80, "trunk_link": 45,
    "primary": 60, "primary_link": 40,
    "secondary": 50, "secondary_link": 35,
    "tertiary": 40, "tertiary_link": 30,
    "unclassified": 30,
    "residential": 25,
    "living_street": 15,
    "service": 15,
    "track": 15,
    "road": 30,
}
FALLBACK_SPEED_KPH = 25

FORMAT_VERSION = 1


# --------------------------------------------------------------------------
# Petites fonctions utilitaires
# --------------------------------------------------------------------------

def _first(value):
    """Après simplification, osmnx peut stocker une liste (plusieurs rues fusionnées)."""
    if isinstance(value, (list, tuple)):
        return value[0] if value else None
    return value


def _name(value) -> str:
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return ""
    if isinstance(value, (list, tuple)):
        return " / ".join(dict.fromkeys(str(v) for v in value if v))
    return str(value)


def _speed(data: dict) -> float:
    speed = data.get("speed_kph")
    if speed is not None and not (isinstance(speed, float) and np.isnan(speed)) and speed > 0:
        return float(speed)
    return float(DEFAULT_SPEEDS_KPH.get(_first(data.get("highway")), FALLBACK_SPEED_KPH))


def _edge_coords(data: dict, xu: float, yu: float, xv: float, yv: float) -> list[tuple[float, float]]:
    """Tracé de l'arête, orienté de u vers v, en (lon, lat)."""
    geom = data.get("geometry")
    if geom is None:
        return [(xu, yu), (xv, yv)]
    coords = list(geom.coords)
    # Par sécurité : on s'assure que le tracé commence bien au nœud de départ.
    d_start = (coords[0][0] - xu) ** 2 + (coords[0][1] - yu) ** 2
    d_end = (coords[-1][0] - xu) ** 2 + (coords[-1][1] - yu) ** 2
    if d_end < d_start:
        coords.reverse()
    return coords


# --------------------------------------------------------------------------
# Étape 1 : téléchargement
# --------------------------------------------------------------------------

def download(place: str):
    """Télécharge le réseau routier carrossable de la zone et sa frontière."""
    import osmnx as ox

    ox.settings.use_cache = True          # cache/ évite de retélécharger à chaque essai
    ox.settings.log_console = True
    ox.settings.requests_timeout = 300

    print(f"[1/4] Frontière de la zone : {place}")
    # Une valeur du type "R1234567" désigne directement une relation OSM.
    by_osmid = place[:1] in "RWN" and place[1:].isdigit()
    boundary = ox.geocode_to_gdf(place, by_osmid=by_osmid)
    polygon = boundary.geometry.iloc[0]
    # VÉRIFIER ce nom et cette emprise : si ce n'est pas le département de
    # l'Atlantique, relancer avec --place R<id de la relation OSM>.
    print(f"      Trouvé : {boundary['display_name'].iloc[0]}")
    print(f"      Emprise (lon/lat) : {[round(v, 3) for v in polygon.bounds]}")

    print("[2/4] Téléchargement du réseau routier (quelques minutes la première fois)")
    G = ox.graph_from_polygon(
        polygon,
        network_type="drive",     # routes carrossables uniquement
        simplify=True,            # fusionne les points intermédiaires d'une même rue
        retain_all=False,
        truncate_by_edge=True,    # garde les routes qui sortent légèrement de la zone
    )

    # On ne garde que la plus grande composante FORTEMENT connexe :
    # depuis n'importe quel nœud, on peut atteindre n'importe quel autre en
    # respectant les sens uniques. Sinon Dijkstra échouerait sur certains trajets.
    before = G.number_of_nodes()
    G = ox.truncate.largest_component(G, strongly=True)
    print(f"      Composante principale : {G.number_of_nodes()} nœuds sur {before}")

    G = ox.add_edge_speeds(G, hwy_speeds=DEFAULT_SPEEDS_KPH, fallback=FALLBACK_SPEED_KPH)
    return G, boundary


# --------------------------------------------------------------------------
# Étape 2 : conversion en tableaux CSR (fonction pure, testée)
# --------------------------------------------------------------------------

def to_arrays(G) -> dict:
    """
    Convertit un MultiDiGraph osmnx en tableaux NumPy au format CSR.

    Règles :
      - les boucles (u == v) sont supprimées ;
      - entre deux nœuds u -> v, on garde une seule arête : la plus courte ;
      - les nœuds sont renumérotés de 0 à N-1 (ordre croissant des id OSM) ;
      - les arêtes sont triées par nœud de départ, puis par nœud d'arrivée.
        L'identifiant d'une arête est sa position dans ces tableaux.
    """
    # 1. Une seule arête par couple (u, v) : la plus courte
    best: dict[tuple[int, int], dict] = {}
    for u, v, data in G.edges(data=True):
        if u == v:
            continue
        current = best.get((u, v))
        if current is None or data["length"] < current["length"]:
            best[(u, v)] = data

    # 2. Renumérotation des nœuds
    node_osmids = np.array(sorted(G.nodes), dtype=np.int64)
    index = {osmid: i for i, osmid in enumerate(node_osmids.tolist())}
    n_nodes = len(node_osmids)

    node_coords = np.empty((n_nodes, 2), dtype=np.float64)
    for osmid, i in index.items():
        node_coords[i, 0] = G.nodes[osmid]["x"]   # longitude
        node_coords[i, 1] = G.nodes[osmid]["y"]   # latitude

    # 3. Tri des arêtes par (départ, arrivée)
    edges = sorted(best.items(), key=lambda item: (index[item[0][0]], index[item[0][1]]))
    n_edges = len(edges)

    sources = np.empty(n_edges, dtype=np.int32)
    targets = np.empty(n_edges, dtype=np.int32)
    lengths = np.empty(n_edges, dtype=np.float64)
    speeds = np.empty(n_edges, dtype=np.float32)
    way_ids = np.empty(n_edges, dtype=np.int64)
    name_ids = np.empty(n_edges, dtype=np.int32)
    highway_ids = np.empty(n_edges, dtype=np.int16)

    names: list[str] = []
    name_index: dict[str, int] = {}
    highways: list[str] = []
    highway_index: dict[str, int] = {}

    geom_offsets = np.empty(n_edges + 1, dtype=np.int64)
    geom_chunks: list[list[tuple[float, float]]] = []
    geom_offsets[0] = 0

    for e, ((u, v), data) in enumerate(edges):
        iu, iv = index[u], index[v]
        sources[e] = iu
        targets[e] = iv
        lengths[e] = float(data["length"])
        speeds[e] = _speed(data)
        way = _first(data.get("osmid"))
        way_ids[e] = int(way) if way is not None else -1

        name = _name(data.get("name"))
        if name not in name_index:
            name_index[name] = len(names)
            names.append(name)
        name_ids[e] = name_index[name]

        highway = str(_first(data.get("highway")) or "unknown")
        if highway not in highway_index:
            highway_index[highway] = len(highways)
            highways.append(highway)
        highway_ids[e] = highway_index[highway]

        coords = _edge_coords(data, *node_coords[iu], *node_coords[iv])
        geom_chunks.append(coords)
        geom_offsets[e + 1] = geom_offsets[e] + len(coords)

    geom_coords = (
        np.array([c for chunk in geom_chunks for c in chunk], dtype=np.float64)
        if geom_chunks else np.empty((0, 2), dtype=np.float64)
    )

    # 4. Tableau offsets (format CSR) : les arêtes sortant du nœud u sont
    #    les indices offsets[u] .. offsets[u+1]-1
    counts = np.bincount(sources, minlength=n_nodes)
    offsets = np.zeros(n_nodes + 1, dtype=np.int64)
    np.cumsum(counts, out=offsets[1:])

    return {
        "offsets": offsets,
        "sources": sources,
        "targets": targets,
        "lengths": lengths,
        "speeds": speeds,
        "way_ids": way_ids,
        "name_ids": name_ids,
        "highway_ids": highway_ids,
        "node_coords": node_coords,
        "node_osmids": node_osmids,
        "geom_offsets": geom_offsets,
        "geom_coords": geom_coords,
        "names": names,
        "highways": highways,
    }


# --------------------------------------------------------------------------
# Étape 3 : sauvegarde
# --------------------------------------------------------------------------

def save(arrays: dict, out_dir: Path, place: str, boundary=None, geojson: bool = False) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)

    for key, value in arrays.items():
        if isinstance(value, np.ndarray):
            np.save(out_dir / f"{key}.npy", value)

    (out_dir / "names.json").write_text(json.dumps(arrays["names"], ensure_ascii=False), encoding="utf-8")
    (out_dir / "highways.json").write_text(json.dumps(arrays["highways"]), encoding="utf-8")

    coords = arrays["node_coords"]
    meta = {
        "format_version": FORMAT_VERSION,
        "place": place,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "n_nodes": int(len(arrays["node_osmids"])),
        "n_edges": int(len(arrays["targets"])),
        "bbox": [float(coords[:, 0].min()), float(coords[:, 1].min()),
                 float(coords[:, 0].max()), float(coords[:, 1].max())],
        "units": {"lengths": "m", "speeds": "km/h", "coords": "lon, lat (EPSG:4326)"},
    }
    (out_dir / "meta.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")

    if boundary is not None:
        boundary[["geometry"]].to_file(out_dir / "boundary.geojson", driver="GeoJSON")

    if geojson:
        features = []
        go, gc = arrays["geom_offsets"], arrays["geom_coords"]
        for e in range(meta["n_edges"]):
            features.append({
                "type": "Feature",
                "id": e,
                "geometry": {"type": "LineString", "coordinates": gc[go[e]:go[e + 1]].tolist()},
                "properties": {
                    "name": arrays["names"][arrays["name_ids"][e]],
                    "highway": arrays["highways"][arrays["highway_ids"][e]],
                    "way_id": int(arrays["way_ids"][e]),
                    "length_m": round(float(arrays["lengths"][e]), 1),
                },
            })
        (out_dir / "edges.geojson").write_text(
            json.dumps({"type": "FeatureCollection", "features": features}), encoding="utf-8")


# --------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="OSM -> graphe CSR")
    parser.add_argument("--place", default="Atlantique, Bénin",
                        help="Zone à télécharger (nom reconnu par Nominatim)")
    parser.add_argument("--out", default=str(Path(__file__).resolve().parent.parent / "data" / "graph"))
    parser.add_argument("--geojson", action="store_true", help="Exporter aussi edges.geojson")
    args = parser.parse_args()

    t0 = time.perf_counter()
    G, boundary = download(args.place)
    print("[3/4] Conversion au format CSR")
    arrays = to_arrays(G)
    print(f"[4/4] Sauvegarde dans {args.out}")
    save(arrays, Path(args.out), args.place, boundary, args.geojson)
    print(f"Terminé en {time.perf_counter() - t0:.0f} s : "
          f"{len(arrays['node_osmids'])} nœuds, {len(arrays['targets'])} arêtes")


if __name__ == "__main__":
    main()
