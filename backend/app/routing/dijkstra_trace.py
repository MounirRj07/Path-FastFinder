"""
dijkstra_trace.py - Dijkstra "avec trace" pour la visualisation pédagogique.

Même algorithme, même tas binaire et mêmes résultats que dijkstra.py ; la seule
différence est qu'on enregistre, étape par étape :
  - quel sommet est fixé (celui de plus petite distance dans le tas) ;
  - quelles arêtes sortantes sont examinées, et si la distance du voisin
    est améliorée, conservée ou si la route est fermée.

À n'utiliser que sur de courts trajets : l'historique est renvoyé au navigateur.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

import numpy as np
from numba import njit

from app.routing.dijkstra import _heap_pop, _heap_push, reconstruct_path

# Statuts d'une arête examinée
STATUS_KEPT = 0       # new_distance >= distance déjà connue : pas d'amélioration
STATUS_IMPROVED = 1   # la distance du voisin est améliorée
STATUS_CLOSED = 2     # coût infini (route fermée) : jamais empruntée

STATUS_NAMES = {STATUS_KEPT: "kept", STATUS_IMPROVED: "improved", STATUS_CLOSED: "closed"}


@njit(cache=True)
def _dijkstra_trace_numba(offsets, targets, costs, source, target, max_nodes, max_events):
    number_of_nodes = len(offsets) - 1
    number_of_edges = len(targets)

    distances = np.full(number_of_nodes, np.inf)
    previous_nodes = np.full(number_of_nodes, -1, dtype=np.int64)
    previous_edges = np.full(number_of_nodes, -1, dtype=np.int64)

    heap_nodes = np.empty(number_of_edges + 1, dtype=np.int64)
    heap_distances = np.empty(number_of_edges + 1, dtype=np.float64)
    heap_size = 0

    # Historique : sommets fixés, dans l'ordre
    settled = np.empty(max_nodes, dtype=np.int64)
    settled_dist = np.empty(max_nodes, dtype=np.float64)
    # Historique : arêtes examinées (ev_step = indice du sommet fixé correspondant)
    ev_step = np.empty(max_events, dtype=np.int64)
    ev_edge = np.empty(max_events, dtype=np.int64)
    ev_status = np.empty(max_events, dtype=np.int8)
    ev_old = np.empty(max_events, dtype=np.float64)
    ev_new = np.empty(max_events, dtype=np.float64)

    n_settled = 0
    n_events = 0
    found = False
    truncated = False

    distances[source] = 0.0
    heap_size = _heap_push(heap_nodes, heap_distances, heap_size, source, 0.0)

    while heap_size > 0:
        current_node, current_distance, heap_size = _heap_pop(
            heap_nodes, heap_distances, heap_size
        )

        # Ignorer les anciennes entrées de la file
        if current_distance != distances[current_node]:
            continue

        # Trop de sommets : on arrête la trace (trajet trop long pour l'affichage)
        if n_settled >= max_nodes:
            truncated = True
            break

        step = n_settled
        settled[step] = current_node
        settled_dist[step] = current_distance
        n_settled += 1

        # Arrêt anticipé lorsque la destination est fixée
        if current_node == target:
            found = True
            break

        for edge_index in range(offsets[current_node], offsets[current_node + 1]):
            neighbor = targets[edge_index]
            edge_cost = costs[edge_index]

            ev_step[n_events] = step
            ev_edge[n_events] = edge_index
            ev_old[n_events] = distances[neighbor]

            if np.isinf(edge_cost):
                ev_status[n_events] = 2
                ev_new[n_events] = np.inf
                n_events += 1
                continue

            new_distance = current_distance + edge_cost
            ev_new[n_events] = new_distance

            if new_distance < distances[neighbor]:
                ev_status[n_events] = 1
                distances[neighbor] = new_distance
                previous_nodes[neighbor] = current_node
                previous_edges[neighbor] = edge_index
                heap_size = _heap_push(
                    heap_nodes, heap_distances, heap_size, neighbor, new_distance
                )
            else:
                ev_status[n_events] = 0
            n_events += 1

    return (
        settled[:n_settled], settled_dist[:n_settled],
        ev_step[:n_events], ev_edge[:n_events], ev_status[:n_events],
        ev_old[:n_events], ev_new[:n_events],
        distances, previous_nodes, previous_edges,
        found, truncated,
    )


@dataclass
class TraceResult:
    source: int
    target: int
    settled: np.ndarray
    settled_dist: np.ndarray
    ev_step: np.ndarray
    ev_edge: np.ndarray
    ev_status: np.ndarray
    ev_old: np.ndarray
    ev_new: np.ndarray
    distances: np.ndarray
    previous_nodes: np.ndarray
    previous_edges: np.ndarray
    found: bool
    truncated: bool


def dijkstra_trace(offsets, targets, costs, source, target, max_nodes=2000) -> TraceResult:
    offsets = np.asarray(offsets, dtype=np.int64)
    targets = np.asarray(targets, dtype=np.int64)
    costs = np.asarray(costs, dtype=np.float64)

    n = len(offsets) - 1
    if not 0 <= source < n or not 0 <= target < n:
        raise ValueError("Indice source ou destination invalide.")
    if max_nodes < 1:
        raise ValueError("max_nodes doit être >= 1.")

    max_nodes = min(int(max_nodes), n)
    max_degree = int(np.max(np.diff(offsets))) if n > 0 else 0
    # Chaque sommet fixé produit au plus `max_degree` événements : jamais de débordement.
    max_events = max(1, max_nodes * max_degree)

    out = _dijkstra_trace_numba(
        offsets, targets, costs, int(source), int(target), max_nodes, max_events
    )
    return TraceResult(int(source), int(target), *out)


def _num(x: float):
    """JSON n'accepte pas l'infini : on renvoie null."""
    return round(float(x), 3) if np.isfinite(x) else None


def build_trace_payload(graph, admin_factors, trace: TraceResult, elapsed_ms: float) -> dict:
    """Met la trace au format JSON envoyé au frontend."""
    n_settled = len(trace.settled)
    n_events = len(trace.ev_edge)

    # Événements regroupés par sommet fixé (ev_step est croissant)
    starts = np.searchsorted(trace.ev_step, np.arange(n_settled), side="left")
    ends = np.append(starts[1:], n_events)

    steps = []
    for i in range(n_settled):
        relax = []
        for k in range(int(starts[i]), int(ends[i])):
            e = int(trace.ev_edge[k])
            relax.append({
                "edge": e,
                "to": int(graph.targets[e]),
                "status": STATUS_NAMES[int(trace.ev_status[k])],
                "old_dist": _num(trace.ev_old[k]),
                "new_dist": _num(trace.ev_new[k]),
            })
        steps.append({
            "node": int(trace.settled[i]),
            "dist": _num(trace.settled_dist[i]),
            "relax": relax,
        })

    # Arêtes distinctes examinées (le tracé n'est envoyé qu'une fois)
    edge_ids = np.unique(trace.ev_edge)
    edges = []
    for e in edge_ids.tolist():
        factor = float(admin_factors[e])
        closed = not np.isfinite(factor)
        edges.append({
            "id": e,
            "from": int(graph.sources[e]),
            "to": int(graph.targets[e]),
            "length_m": round(float(graph.lengths[e]), 1),
            "factor": None if closed else round(factor, 2),
            "cost": None if closed else round(float(graph.lengths[e]) * factor, 1),
            "name": graph.edge_name(e),
            "geometry": np.round(graph.edge_geometry(e), 6).tolist(),
        })

    # Sommets concernés : fixés + voisins découverts
    node_ids = np.unique(np.concatenate([
        trace.settled.astype(np.int64),
        graph.targets[edge_ids].astype(np.int64),
        np.array([trace.source, trace.target], dtype=np.int64),
    ]))
    nodes = [
        {"id": int(v),
         "lon": round(float(graph.node_coords[v, 0]), 6),
         "lat": round(float(graph.node_coords[v, 1]), 6)}
        for v in node_ids
    ]

    # Chemin final reconstruit
    path = None
    if trace.found:
        path_edges = reconstruct_path(
            trace.source, trace.target, trace.previous_nodes, trace.previous_edges
        )
        path_nodes = [trace.source] + [int(graph.targets[e]) for e in path_edges]
        path = {
            "edges": path_edges,
            "nodes": path_nodes,
            "distance_m": round(float(graph.lengths[path_edges].sum()), 1) if path_edges else 0.0,
            "cost": _num(trace.distances[trace.target]),
        }

    return {
        "source": trace.source,
        "target": trace.target,
        "nodes": nodes,
        "edges": edges,
        "steps": steps,
        "path": path,
        "stats": {
            "nodes_explored": n_settled,
            "edges_examined": n_events,
            "found": trace.found,
            "truncated": trace.truncated,
            "compute_time_ms": round(elapsed_ms, 1),
        },
    }


def timed_trace(graph, admin_factors, source, target, max_nodes=2000) -> dict:
    """Calcule la trace complète et renvoie le JSON prêt à envoyer."""
    costs = graph.lengths * admin_factors
    t0 = time.perf_counter()
    trace = dijkstra_trace(graph.offsets, graph.targets, costs, source, target, max_nodes)
    elapsed_ms = (time.perf_counter() - t0) * 1000
    return build_trace_payload(graph, admin_factors, trace, elapsed_ms)