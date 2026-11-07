
from dataclasses import dataclass

import numpy as np

from app.routing.dijkstra import (
    dijkstra_csr,
    reconstruct_path,
)


# Facteur de pénalisation temporaire pour générer des alternatives.
ALTERNATIVE_FACTOR = 1.4

# Pourcentage maximal de distance commune entre deux itinéraires.
MAX_SHARED_RATIO = 0.70

# Distance maximale d'une alternative par rapport à l'itinéraire principal.
MAX_DISTANCE_RATIO = 1.5


@dataclass
class Route:
    nodes: list
    edges: list
    distance_m: float
    duration_s: float
    penalized_edges: list


def _build_route(
    source,
    target,
    previous_nodes,
    previous_edges,
    lengths,
    speeds,
    admin_factors,
):
    """
    Reconstruit un itinéraire à partir des tableaux de prédécesseurs
    produits par Dijkstra.
    """

    edge_ids = reconstruct_path(
        source,
        target,
        previous_nodes,
        previous_edges,
    )

    if source != target and not edge_ids:
        return None

    # Reconstruction correcte des nœuds dans l'ordre du parcours.
    route_nodes = [int(target)]
    current = target

    while current != source:
        current = int(previous_nodes[current])

        if current < 0:
            return None

        route_nodes.append(current)

    route_nodes.reverse()

    # Calcul de la distance totale.
    distance_m = float(np.sum(lengths[edge_ids]))

    # Calcul de la durée estimée en secondes.
    duration_s = float(
        np.sum(
            lengths[edge_ids] * 3.6 / speeds[edge_ids]
        )
    )

    # Identification des arêtes pénalisées administrativement.
    if admin_factors is None:
        penalized_edges = []
    else:
        penalized_edges = [
            int(edge)
            for edge in edge_ids
            if admin_factors[edge] > 1.0
        ]

    return Route(
        nodes=route_nodes,
        edges=[int(edge) for edge in edge_ids],
        distance_m=distance_m,
        duration_s=duration_s,
        penalized_edges=penalized_edges,
    )


def _shared_length(candidate, previous_routes, lengths):
    """
    Calcule le taux maximal de distance partagée entre un candidat
    et les itinéraires déjà sélectionnés.
    """

    if candidate.distance_m <= 0:
        return 0.0

    candidate_edges = set(candidate.edges)

    max_ratio = 0.0

    for route in previous_routes:
        previous_edges = set(route.edges)

        common_edges = candidate_edges.intersection(
            previous_edges
        )

        shared_distance = float(
            np.sum(lengths[list(common_edges)])
        )

        ratio = shared_distance / candidate.distance_m

        max_ratio = max(max_ratio, ratio)

    return max_ratio

def _is_valid_alternative(
    candidate,
    previous_routes,
    primary_distance,
    lengths,
):
    """
    Vérifie si un itinéraire candidat est suffisamment différent
    de l'itinéraire principal et des itinéraires déjà sélectionnés.
    """

    if primary_distance <= 0:
        return False

    # Vérification du rapport de distance par rapport à P1.
    if candidate.distance_m > (
        MAX_DISTANCE_RATIO * primary_distance
    ):
        return False

    # Vérification du taux de partage des arêtes.
    shared_ratio = _shared_length(
        candidate,
        previous_routes,
        lengths,
    )

    if shared_ratio > MAX_SHARED_RATIO:
        return False

    return True


def compute_routes(
    offsets,
    targets,
    lengths,
    speeds,
    source,
    target,
    admin_factors=None,
    k=3,
):
    """
    Calcule jusqu'à k itinéraires alternatifs entre une source
    et une destination.

    Le premier itinéraire est calculé avec Dijkstra.
    Les itinéraires suivants sont générés en pénalisant
    temporairement les arêtes des itinéraires déjà explorés.
    """

    # Validation du nombre d'itinéraires demandé.
    if not isinstance(k, (int, np.integer)) or isinstance(k, bool):
        raise ValueError("k doit être un entier.")

    if k < 1 or k > 3:
        raise ValueError("k doit être compris entre 1 et 3.")

    # Conversion des tableaux.
    offsets = np.asarray(offsets)
    targets = np.asarray(targets)
    lengths = np.asarray(lengths, dtype=np.float64)
    speeds = np.asarray(speeds, dtype=np.float64)

    # Validation des dimensions.
    if offsets.ndim != 1 or targets.ndim != 1:
        raise ValueError("offsets et targets doivent être des tableaux 1D.")

    if lengths.ndim != 1 or speeds.ndim != 1:
        raise ValueError("lengths et speeds doivent être des tableaux 1D.")

    if not (
        len(targets) == len(lengths) == len(speeds)
    ):
        raise ValueError(
            "targets, lengths et speeds doivent avoir la même longueur."
        )

    if len(offsets) < 2:
        raise ValueError("Le graphe doit contenir au moins un nœud.")

    if offsets[0] != 0 or offsets[-1] != len(targets):
        raise ValueError("Structure CSR invalide.")

    if np.any(np.diff(offsets) < 0):
        raise ValueError("Les offsets doivent être croissants.")

    if not np.all(np.isfinite(lengths)) or np.any(lengths <= 0):
        raise ValueError("Les longueurs doivent être positives et finies.")

    if not np.all(np.isfinite(speeds)) or np.any(speeds <= 0):
        raise ValueError("Les vitesses doivent être positives et finies.")

    number_of_nodes = len(offsets) - 1
    number_of_edges = len(targets)

    if source < 0 or source >= number_of_nodes:
        raise ValueError("Identifiant source invalide.")

    if target < 0 or target >= number_of_nodes:
        raise ValueError("Identifiant destination invalide.")

    if np.any(targets < 0) or np.any(targets >= number_of_nodes):
        raise ValueError("Le tableau targets contient un nœud invalide.")

    # Gestion des pénalités administratives.
    if admin_factors is None:
        admin_factors = np.ones(
            number_of_edges,
            dtype=np.float64,
        )
    else:
        admin_factors = np.asarray(
            admin_factors,
            dtype=np.float64,
        )

        if admin_factors.ndim != 1:
            raise ValueError("admin_factors doit être un tableau 1D.")

        if len(admin_factors) != number_of_edges:
            raise ValueError(
                "admin_factors doit avoir la même longueur que targets."
            )

        if np.any(np.isnan(admin_factors)) or np.any(admin_factors < 1):
            raise ValueError(
                "Les facteurs administratifs doivent être >= 1 et sans NaN."
            )

    # Coûts de base : longueur multipliée par le facteur administratif.
    base_costs = lengths * admin_factors

    # Premier itinéraire : itinéraire optimal selon les coûts de base.
    distances, previous_nodes, previous_edges, _ = dijkstra_csr(
        offsets,
        targets,
        base_costs,
        source,
        target,
    )

    if not np.isfinite(distances[target]):
        return []

    first_route = _build_route(
        source,
        target,
        previous_nodes,
        previous_edges,
        lengths,
        speeds,
        admin_factors,
    )

    if first_route is None:
        return []

    selected_routes = [first_route]
    explored_routes = [first_route]

    # Génération des itinéraires alternatifs.
    for _ in range(k - 1):

        # Copie des coûts de base.
        temporary_costs = base_costs.copy()

        # Récupération des arêtes des itinéraires explorés.
        explored_edges = set()

        for route in explored_routes:
            explored_edges.update(route.edges)

        # Pénalisation temporaire des arêtes déjà explorées.
        for edge in explored_edges:
            if np.isfinite(temporary_costs[edge]):
                temporary_costs[edge] *= ALTERNATIVE_FACTOR

        # Nouveau calcul avec Dijkstra.
        distances, previous_nodes, previous_edges, _ = dijkstra_csr(
            offsets,
            targets,
            temporary_costs,
            source,
            target,
        )

        if not np.isfinite(distances[target]):
            break

        candidate = _build_route(
            source,
            target,
            previous_nodes,
            previous_edges,
            lengths,
            speeds,
            admin_factors,
        )

        if candidate is None:
            break

        explored_routes.append(candidate)

        # Vérification de la pertinence de l'alternative.
        if _is_valid_alternative(
            candidate,
            selected_routes,
            first_route.distance_m,
            lengths,
        ):
            selected_routes.append(candidate)

    return selected_routes
