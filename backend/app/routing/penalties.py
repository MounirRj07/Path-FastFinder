from datetime import datetime, timezone
import numpy as np


PENALTY_FACTORS = {
    "light": 1.5,
    "medium": 3.0,
    "high": 10.0,
    "closed": np.inf,
}


def parse_datetime(value):
    """
    Convertit une date ISO 8601 en datetime avec fuseau horaire UTC.
    """

    if value is None:
        return None

    if isinstance(value, str):
        value = datetime.fromisoformat(
            value.replace("Z", "+00:00")
        )

    if not isinstance(value, datetime):
        raise ValueError("Date de pénalité invalide.")

    if value.tzinfo is None:
        raise ValueError("La date doit contenir un fuseau horaire.")

    return value.astimezone(timezone.utc)


def build_admin_factors(number_of_edges, penalties, now=None):
    """
    Construit un tableau de facteurs administratifs.

    Chaque indice du tableau correspond à un identifiant d'arête.

    Si plusieurs pénalités actives concernent la même arête,
    seul le facteur maximal est conservé.
    """

    if number_of_edges < 0:
        raise ValueError("Le nombre d'arêtes ne peut pas être négatif.")

    if now is None:
        now = datetime.now(timezone.utc)
    else:
        now = parse_datetime(now)

    factors = np.ones(number_of_edges, dtype=np.float64)

    for penalty in penalties:

        edge_id = int(penalty["edge_id"])

        if not 0 <= edge_id < number_of_edges:
            raise ValueError(f"Identifiant d'arête invalide : {edge_id}")

        if not penalty.get("is_active", True):
            continue

        level = penalty["level"].lower()

        if level not in PENALTY_FACTORS:
            raise ValueError(f"Niveau de pénalité inconnu : {level}")

        starts_at = parse_datetime(penalty.get("starts_at"))
        ends_at = parse_datetime(penalty.get("ends_at"))

        # La pénalité n'est pas encore entrée en vigueur.
        if starts_at is not None and now < starts_at:
            continue

        # La pénalité a expiré.
        if ends_at is not None and now >= ends_at:
            continue

        factor = PENALTY_FACTORS[level]

        # Conserver le facteur maximal.
        factors[edge_id] = max(factors[edge_id], factor)

    return factors


def apply_admin_penalties(base_costs, admin_factors):
    """
    Calcule les coûts après application des pénalités.

    Les tableaux originaux ne sont pas modifiés.
    """

    base_costs = np.asarray(base_costs, dtype=np.float64)
    admin_factors = np.asarray(admin_factors, dtype=np.float64)

    if base_costs.ndim != 1 or admin_factors.ndim != 1:
        raise ValueError("Les tableaux doivent être unidimensionnels.")

    if len(base_costs) != len(admin_factors):
        raise ValueError(
            "Les coûts et les facteurs doivent avoir la même longueur."
        )

    if np.any(np.isnan(base_costs)) or np.any(base_costs < 0):
        raise ValueError("Les coûts de base doivent être positifs ou nuls.")

    if np.any(np.isnan(admin_factors)) or np.any(admin_factors < 1):
        raise ValueError("Les facteurs administratifs doivent être >= 1.")

    effective_costs = base_costs * admin_factors

    return effective_costs