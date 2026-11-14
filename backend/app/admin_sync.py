"""
Synchronisation des pénalités : PostgreSQL -> tableau admin_factors en RAM.

Appelé au démarrage, après chaque écriture admin, et toutes les minutes
(pour activer ou désactiver les pénalités selon leurs dates).
"""

import os
from datetime import datetime, timezone

import numpy as np
import psycopg

from app.routing.penalties import PENALTY_FACTORS, build_admin_factors

SYNC_INTERVAL_S = 60


def rebuild_admin_state(app) -> None:
    graph = app.state.graph
    dsn = os.environ.get("DATABASE_URL")
    now = datetime.now(timezone.utc)

    if not dsn:
        print("ATTENTION : DATABASE_URL absent, aucune pénalité chargée")
        app.state.admin_factors = np.ones(graph.n_edges, dtype=np.float64)
        app.state.penalty_index = {}
        return

    with psycopg.connect(dsn) as conn:
        rows = conn.execute(
            "select id, edge_ids, level, reason, starts_at, ends_at "
            "from penalties where deleted_at is null"
        ).fetchall()

    penalties = []
    index = {}  # arête -> pénalité active la plus forte (pour l'affichage)

    for _pid, edge_ids, level, reason, starts_at, ends_at in rows:
        for edge_id in edge_ids:
            penalties.append({
                "edge_id": edge_id,
                "level": level,
                "starts_at": starts_at,
                "ends_at": ends_at,
            })
            if starts_at <= now < ends_at:
                current = index.get(edge_id)
                if current is None or PENALTY_FACTORS[level] > PENALTY_FACTORS[current["level"]]:
                    index[edge_id] = {"level": level, "reason": reason}

    app.state.admin_factors = build_admin_factors(graph.n_edges, penalties, now=now)
    app.state.penalty_index = index