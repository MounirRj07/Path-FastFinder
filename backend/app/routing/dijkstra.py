import numpy as np
from numba import njit


@njit(cache=True)
def _heap_push(heap_nodes, heap_distances, size, node, distance):
    index = size

    heap_nodes[index] = node
    heap_distances[index] = distance

    while index > 0:
        parent = (index - 1) // 2

        if heap_distances[parent] <= heap_distances[index]:
            break

        heap_nodes[parent], heap_nodes[index] = (
            heap_nodes[index],
            heap_nodes[parent]
        )

        heap_distances[parent], heap_distances[index] = (
            heap_distances[index],
            heap_distances[parent]
        )

        index = parent

    return size + 1


@njit(cache=True)
def _heap_pop(heap_nodes, heap_distances, size):
    node = heap_nodes[0]
    distance = heap_distances[0]

    size -= 1

    if size > 0:
        heap_nodes[0] = heap_nodes[size]
        heap_distances[0] = heap_distances[size]

        index = 0

        while True:
            left = 2 * index + 1
            right = 2 * index + 2
            smallest = index

            if left < size:
                if heap_distances[left] < heap_distances[smallest]:
                    smallest = left

            if right < size:
                if heap_distances[right] < heap_distances[smallest]:
                    smallest = right

            if smallest == index:
                break

            heap_nodes[index], heap_nodes[smallest] = (
                heap_nodes[smallest],
                heap_nodes[index]
            )

            heap_distances[index], heap_distances[smallest] = (
                heap_distances[smallest],
                heap_distances[index]
            )

            index = smallest

    return node, distance, size


@njit(cache=True)
def _dijkstra_csr_numba(offsets, targets, costs, source, target):

    number_of_nodes = len(offsets) - 1
    number_of_edges = len(targets)

    distances = np.full(number_of_nodes, np.inf)
    previous_nodes = np.full(number_of_nodes, -1, dtype=np.int64)
    previous_edges = np.full(number_of_nodes, -1, dtype=np.int64)

    heap_nodes = np.empty(number_of_edges + 1, dtype=np.int64)
    heap_distances = np.empty(number_of_edges + 1, dtype=np.float64)

    heap_size = 0
    explored = 0

    distances[source] = 0.0

    heap_size = _heap_push(
        heap_nodes,
        heap_distances,
        heap_size,
        source,
        0.0
    )

    while heap_size > 0:

        current_node, current_distance, heap_size = _heap_pop(
            heap_nodes,
            heap_distances,
            heap_size
        )

        # Ignorer les anciennes entrées de la file
        if current_distance != distances[current_node]:
            continue

        explored += 1

        # Arrêt anticipé lorsque la destination est atteinte
        if current_node == target:
            break

        # Parcourir les voisins du sommet courant
        for edge_index in range(
            offsets[current_node],
            offsets[current_node + 1]
        ):

            neighbor = targets[edge_index]
            edge_cost = costs[edge_index]

            # Ignorer les arêtes fermées
            if np.isinf(edge_cost):
                continue

            new_distance = current_distance + edge_cost

            if new_distance < distances[neighbor]:

                distances[neighbor] = new_distance

                previous_nodes[neighbor] = current_node
                previous_edges[neighbor] = edge_index

                heap_size = _heap_push(
                    heap_nodes,
                    heap_distances,
                    heap_size,
                    neighbor,
                    new_distance
                )

    return distances, previous_nodes, previous_edges, explored


def dijkstra_csr(offsets, targets, costs, source, target):

    offsets = np.asarray(offsets, dtype=np.int64)
    targets = np.asarray(targets, dtype=np.int64)
    costs = np.asarray(costs, dtype=np.float64)

    if offsets.ndim != 1 or targets.ndim != 1 or costs.ndim != 1:
        raise ValueError("Les tableaux CSR doivent être unidimensionnels.")

    if len(offsets) == 0:
        raise ValueError("Le tableau offsets ne peut pas être vide.")

    number_of_nodes = len(offsets) - 1

    if offsets[0] != 0:
        raise ValueError("offsets doit commencer par 0.")

    if offsets[-1] != len(targets):
        raise ValueError("Le dernier offset doit correspondre au nombre d'arêtes.")

    if len(targets) != len(costs):
        raise ValueError("targets et costs doivent avoir la même longueur.")

    if np.any(np.diff(offsets) < 0):
        raise ValueError("Les offsets doivent être croissants.")

    if np.any(targets < 0) or np.any(targets >= number_of_nodes):
        raise ValueError("Un sommet cible possède un indice invalide.")

    if np.any(np.isnan(costs)) or np.any(costs < 0):
        raise ValueError("Les coûts doivent être positifs ou nuls.")

    if not 0 <= source < number_of_nodes:
        raise ValueError("Indice source invalide.")

    if not 0 <= target < number_of_nodes:
        raise ValueError("Indice destination invalide.")

    return _dijkstra_csr_numba(
        offsets,
        targets,
        costs,
        source,
        target
    )


def reconstruct_path(source, target, previous_nodes, previous_edges):

    if source == target:
        return []

    if previous_nodes[target] == -1:
        return []

    path_edges = []
    current_node = target

    while current_node != source:

        edge_index = previous_edges[current_node]

        if edge_index == -1:
            return []

        path_edges.append(int(edge_index))

        current_node = previous_nodes[current_node]

    path_edges.reverse()

    return path_edges
