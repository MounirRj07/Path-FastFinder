"""
main.py - Point d'entrée de l'API Path-FastFinder.

Routes publiques : /route, /places, /penalties/active, /health.
Routes administrateur (jeton Supabase + rôle admin) : /admin/*.
"""

import asyncio
import os
import time
from contextlib import asynccontextmanager, suppress
from datetime import datetime, timezone
from typing import Literal

import numpy as np
import psycopg
from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import AwareDatetime, BaseModel, Field, model_validator

from app.admin_sync import SYNC_INTERVAL_S, rebuild_admin_state
from app.auth import require_admin
from app.routing.alternatives import compute_routes
from app.routing.graph import Graph
from app.routing.penalties import PENALTY_FACTORS
from app.routing.snapping import OutOfZoneError, Snapper
from fastapi.middleware.gzip import GZipMiddleware
from app.routing.dijkstra_trace import timed_trace


async def _periodic_sync(app: FastAPI) -> None:
    while True:
        await asyncio.sleep(SYNC_INTERVAL_S)
        try:
            await asyncio.to_thread(rebuild_admin_state, app)
        except Exception as exc:
            print(f"Synchronisation des pénalités échouée : {exc}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    t0 = time.perf_counter()
    graph = Graph.load(os.environ.get("GRAPH_PATH", "../data/graph"))
    app.state.graph = graph
    app.state.snapper = Snapper(graph)
    app.state.load_time_s = round(time.perf_counter() - t0, 2)
    print(f"Graphe chargé : {graph.n_nodes} nœuds, {graph.n_edges} arêtes "
          f"en {app.state.load_time_s} s")

    # Précompilation de Dijkstra (Numba) pour que le premier utilisateur n'attende pas.
    timed_trace(graph, np.ones(graph.n_edges), 0, min(50, graph.n_nodes - 1), max_nodes=100)
    print("Trace Dijkstra précompilée")
    t1 = time.perf_counter()
    compute_routes(graph.offsets, graph.targets, graph.lengths, graph.speeds,
                   0, graph.n_nodes - 1, admin_factors=np.ones(graph.n_edges), k=1)
    app.state.warmup_time_s = round(time.perf_counter() - t1, 2)
    print(f"Dijkstra précompilé en {app.state.warmup_time_s} s")

    rebuild_admin_state(app)
    sync_task = asyncio.create_task(_periodic_sync(app))
    yield
    sync_task.cancel()
    with suppress(asyncio.CancelledError):
        await sync_task


app = FastAPI(title="Path-FastFinder API", lifespan=lifespan)
app.add_middleware(GZipMiddleware, minimum_size=1000)

# En production, FRONTEND_URL doit contenir l'URL Vercel du frontend.
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get("FRONTEND_URL", "http://localhost:3000").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)


def db():
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        raise HTTPException(status_code=500, detail="DATABASE_URL manquant")
    return psycopg.connect(dsn)


def _check_edges(graph: Graph, edge_ids: list[int]) -> None:
    bad = [e for e in edge_ids if not 0 <= e < graph.n_edges]
    if bad:
        raise HTTPException(status_code=422, detail=f"Arêtes inconnues : {bad[:5]}")


def _penalty_json(graph: Graph, row) -> dict:
    pid, edge_ids, level, reason, starts_at, ends_at = row
    return {
        "id": pid,
        "level": level,
        "reason": reason,
        "starts_at": starts_at,
        "ends_at": ends_at,
        "edge_ids": edge_ids,
        "segments": [graph.edge_geometry(e).tolist() for e in edge_ids],
    }


def _format_route(graph: Graph, route, rank: int, penalty_index: dict) -> dict:
    segments = []
    for edge_id in route.penalized_edges:
        info = penalty_index.get(edge_id)
        if info:
            segments.append({
                "level": info["level"],
                "reason": info["reason"],
                "geometry": graph.edge_geometry(edge_id).tolist(),
            })
    return {
        "rank": rank,
        "distance_m": round(route.distance_m, 1),
        "duration_s": round(route.duration_s, 1),
        "geometry": graph.path_geometry(route.edges),
        "penalized_segments": segments,
    }


# ---------- Modèles admin ----------
class PenaltyIn(BaseModel):
    edge_ids: list[int] = Field(min_length=1)
    level: Literal["light", "medium", "high", "closed"]
    reason: str = Field(min_length=1, max_length=200)
    starts_at: AwareDatetime
    ends_at: AwareDatetime

    @model_validator(mode="after")
    def check_dates(self):
        if self.ends_at <= self.starts_at:
            raise ValueError("ends_at doit être après starts_at")
        return self


class PenaltyPatch(BaseModel):
    level: Literal["light", "medium", "high", "closed"] | None = None
    reason: str | None = Field(default=None, min_length=1, max_length=200)
    starts_at: AwareDatetime | None = None
    ends_at: AwareDatetime | None = None


# ---------- Health ----------
@app.get("/health")
def health(request: Request):
    graph = request.app.state.graph
    return {
        "status": "ok",
        "graph": {
            "place": graph.meta["place"],
            "created_at": graph.meta["created_at"],
            "n_nodes": graph.n_nodes,
            "n_edges": graph.n_edges,
            "load_time_s": request.app.state.load_time_s,
            "warmup_time_s": request.app.state.warmup_time_s,
        },
    }


# ---------- Itinéraire ----------
@app.get("/route")
def get_route(
    request: Request,
    from_lat: float,
    from_lon: float,
    to_lat: float,
    to_lon: float,
    alternatives: int = Query(2, ge=0, le=2),
):
    state = request.app.state
    graph = state.graph
    try:
        source, _ = state.snapper.nearest_node(from_lat, from_lon)
        target, _ = state.snapper.nearest_node(to_lat, to_lon)
    except OutOfZoneError:
        raise HTTPException(status_code=422, detail="Point hors de la zone couverte")

    t0 = time.perf_counter()
    routes = compute_routes(
        graph.offsets, graph.targets, graph.lengths, graph.speeds,
        source, target, admin_factors=state.admin_factors, k=alternatives + 1,
    )
    elapsed_ms = (time.perf_counter() - t0) * 1000

    if not routes:
        raise HTTPException(status_code=404, detail="Aucun itinéraire entre ces deux points")

    return {
        "routes": [
            _format_route(graph, r, i + 1, state.penalty_index)
            for i, r in enumerate(routes)
        ],
        "stats": {"compute_time_ms": round(elapsed_ms, 1)},
    }

# ---------- Visualisation pas à pas de Dijkstra ----------
MAX_TRACE_STRAIGHT_M = 1200   # au-delà, la trace serait trop lourde à afficher


def _straight_distance_m(lat1, lon1, lat2, lon2) -> float:
    import math
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = (math.sin((p2 - p1) / 2) ** 2
         + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2)
    return 2 * 6_371_008.8 * math.asin(math.sqrt(a))


@app.get("/route/trace")
def get_route_trace(
    request: Request,
    from_lat: float,
    from_lon: float,
    to_lat: float,
    to_lon: float,
    max_nodes: int = Query(1200, ge=50, le=2000),
):
    if _straight_distance_m(from_lat, from_lon, to_lat, to_lon) > MAX_TRACE_STRAIGHT_M:
        raise HTTPException(
            status_code=422,
            detail="Trajet trop long pour la visualisation (maximum 1,2 km à vol d'oiseau).",
        )
    state = request.app.state
    try:
        source, _ = state.snapper.nearest_node(from_lat, from_lon)
        target, _ = state.snapper.nearest_node(to_lat, to_lon)
    except OutOfZoneError:
        raise HTTPException(status_code=422, detail="Point hors de la zone couverte")
    return timed_trace(
        state.graph,
        np.asarray(state.admin_factors, dtype=np.float64),
        source, target, max_nodes,
    )

# ---------- Lieux ----------
@app.get("/places")
def places(q: str = Query(..., min_length=2), limit: int = Query(10, ge=1, le=10)):
    with db() as conn:
        rows = conn.execute(
            "select id, name, ST_Y(geom::geometry), ST_X(geom::geometry), "
            "similarity(name, %s) as score "
            "from places "
            "where name %% %s or name ilike %s "
            "order by score desc limit %s",
            (q, q, f"%{q}%", limit),
        ).fetchall()
    return [{"id": r[0], "name": r[1], "lat": r[2], "lon": r[3]} for r in rows]


# ---------- Pénalités actives (public) ----------
@app.get("/penalties/active")
def active_penalties(request: Request):
    graph = request.app.state.graph
    with db() as conn:
        rows = conn.execute(
            "select id, edge_ids, level, reason, starts_at, ends_at from penalties "
            "where deleted_at is null and now() >= starts_at and now() < ends_at "
            "order by starts_at"
        ).fetchall()
    return [_penalty_json(graph, row) for row in rows]


# ---------- Administration ----------
@app.get("/admin/edges/nearest")
def nearest_edge(
    request: Request,
    lat: float,
    lon: float,
    whole_way: bool = False,
    admin_id: str = Depends(require_admin),
):
    state = request.app.state
    try:
        edges = state.snapper.select_road(lat, lon, whole_way=whole_way)
    except OutOfZoneError:
        raise HTTPException(status_code=422, detail="Point hors de la zone couverte")
    if not edges:
        raise HTTPException(status_code=404, detail="Aucune route trouvée")
    graph = state.graph
    return {
        "edge_ids": edges,
        "name": graph.edge_name(edges[0]),
        "highway": graph.edge_highway(edges[0]),
        "geometry": graph.path_geometry(edges),
    }


@app.get("/admin/penalties")
def list_penalties(request: Request, admin_id: str = Depends(require_admin)):
    graph = request.app.state.graph
    now = datetime.now(timezone.utc)
    with db() as conn:
        rows = conn.execute(
            "select id, edge_ids, level, reason, starts_at, ends_at from penalties "
            "where deleted_at is null order by starts_at desc"
        ).fetchall()
    result = []
    for row in rows:
        item = _penalty_json(graph, row)
        if now < row[4]:
            item["status"] = "a_venir"
        elif now < row[5]:
            item["status"] = "active"
        else:
            item["status"] = "passee"
        result.append(item)
    return result


@app.post("/admin/penalties", status_code=201)
def create_penalty(
    body: PenaltyIn,
    request: Request,
    admin_id: str = Depends(require_admin),
):
    graph = request.app.state.graph
    _check_edges(graph, body.edge_ids)
    with db() as conn:
        new_id = conn.execute(
            "insert into penalties (edge_ids, level, factor, reason, starts_at, ends_at, created_by) "
            "values (%s, %s, %s, %s, %s, %s, %s::uuid) returning id",
            (body.edge_ids, body.level, PENALTY_FACTORS[body.level],
             body.reason.strip(), body.starts_at, body.ends_at, admin_id),
        ).fetchone()[0]
    rebuild_admin_state(request.app)
    return {"id": new_id}


@app.patch("/admin/penalties/{penalty_id}")
def update_penalty(
    penalty_id: int,
    body: PenaltyPatch,
    request: Request,
    admin_id: str = Depends(require_admin),
):
    with db() as conn:
        row = conn.execute(
            "select level, reason, starts_at, ends_at from penalties "
            "where id = %s and deleted_at is null",
            (penalty_id,),
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Pénalité introuvable")

        level = body.level or row[0]
        reason = body.reason.strip() if body.reason else row[1]
        starts_at = body.starts_at or row[2]
        ends_at = body.ends_at or row[3]
        if ends_at <= starts_at:
            raise HTTPException(status_code=422, detail="La fin doit être après le début")

        conn.execute(
            "update penalties set level = %s, factor = %s, reason = %s, "
            "starts_at = %s, ends_at = %s where id = %s",
            (level, PENALTY_FACTORS[level], reason, starts_at, ends_at, penalty_id),
        )
    rebuild_admin_state(request.app)
    return {"id": penalty_id}


@app.delete("/admin/penalties/{penalty_id}")
def delete_penalty(
    penalty_id: int,
    request: Request,
    admin_id: str = Depends(require_admin),
):
    with db() as conn:
        row = conn.execute(
            "update penalties set deleted_at = now() "
            "where id = %s and deleted_at is null returning id",
            (penalty_id,),
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Pénalité introuvable")
    rebuild_admin_state(request.app)
    return {"deleted": penalty_id}