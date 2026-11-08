
from dataclasses import dataclass

ETATS_VALIDES = {"fluide", "dense", "tres_dense", "inondee", "bloquee"}


@dataclass
class Itineraire:
    coordinates: list[list[float]]   # [lon, lat]
    distance_m: float
    duration_s: float


class AucunChemin(Exception):
    """Levée quand aucun chemin n'existe entre le départ et l'arrivée."""


def compute_routes(start, end, scenario, road_overrides):
    """start et end sont des tuples (lat, lon).
    Renvoie (itineraire_plus_court, itineraire_plus_rapide).
    """
    # VERSION SIMULÉE
    line = [[start[1], start[0]], [end[1], end[0]]]
    court = Itineraire(line, 3200, 480)
    rapide = Itineraire(line, 3500, 420)
    return court, rapide