import os

import httpx
import psycopg
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from routing import ETATS_VALIDES, AucunChemin, compute_routes

load_dotenv()
DATABASE_URL = os.environ["DATABASE_URL"]
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY")

app = FastAPI(title="API itinéraire secours")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------- Modèles de données ----------
class Point(BaseModel):
    lat: float
    lon: float


class RouteRequest(BaseModel):
    start: Point
    end: Point
    scenario: str | None = None
    road_overrides: dict[str, str] = {}


class RouteResult(BaseModel):
    coordinates: list[list[float]]
    distance_m: float
    duration_s: float


class RouteResponse(BaseModel):
    shortest: RouteResult
    fastest: RouteResult
    identical: bool


class HistoryIn(BaseModel):
    center_id: int | None = None
    end_lat: float
    end_lon: float
    shortest_m: float | None = None
    fastest_s: float | None = None
    scenario: str | None = None


class FavoriteIn(BaseModel):
    center_id: int | None = None
    end_lat: float
    end_lon: float
    label: str | None = None


# ---------- Authentification ----------
def current_user_id(authorization: str | None = Header(default=None)) -> str:
    """Vérifie le jeton de connexion auprès de Supabase et renvoie l'id de l'utilisateur."""
    if not SUPABASE_URL or not SUPABASE_ANON_KEY:
        raise HTTPException(status_code=500, detail="SUPABASE_URL ou SUPABASE_ANON_KEY manquant dans .env")
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Connexion requise")
    r = httpx.get(
        f"{SUPABASE_URL}/auth/v1/user",
        headers={"Authorization": authorization, "apikey": SUPABASE_ANON_KEY},
        timeout=10,
    )
    if r.status_code != 200:
        raise HTTPException(status_code=401, detail="Jeton invalide ou expiré")
    return r.json()["id"]


# ---------- Itinéraire (simulé, remplacé plus tard par Dijkstra) ----------
@app.post("/route", response_model=RouteResponse)
def route(req: RouteRequest):
    inconnus = set(req.road_overrides.values()) - ETATS_VALIDES
    if inconnus:
        raise HTTPException(status_code=422, detail=f"États inconnus : {sorted(inconnus)}")
    try:
        court, rapide = compute_routes(
            (req.start.lat, req.start.lon),
            (req.end.lat, req.end.lon),
            req.scenario,
            req.road_overrides,
        )
    except AucunChemin:
        raise HTTPException(status_code=404, detail="Aucun chemin entre ce centre et ce lieu")
    return RouteResponse(
        shortest=RouteResult(coordinates=court.coordinates, distance_m=court.distance_m, duration_s=court.duration_s),
        fastest=RouteResult(coordinates=rapide.coordinates, distance_m=rapide.distance_m, duration_s=rapide.duration_s),
        identical=court.coordinates == rapide.coordinates,
    )


# ---------- Centres de secours (base de données) ----------
@app.get("/centers")
def centers():
    with psycopg.connect(DATABASE_URL) as conn:
        rows = conn.execute(
            "select id, name, ST_Y(geom::geometry), ST_X(geom::geometry) "
            "from centers order by name"
        ).fetchall()
    return [{"id": r[0], "name": r[1], "lat": r[2], "lon": r[3]} for r in rows]


# ---------- Recherche de lieux (base de données) ----------
@app.get("/places")
def places(q: str = Query(..., min_length=2), limit: int = 8):
    with psycopg.connect(DATABASE_URL) as conn:
        rows = conn.execute(
            "select id, name, ST_Y(geom::geometry), ST_X(geom::geometry), "
            "similarity(name, %s) as score "
            "from places "
            "where name %% %s or name ilike %s "
            "order by score desc limit %s",
            (q, q, f"%{q}%", limit),
        ).fetchall()
    return [{"id": r[0], "name": r[1], "lat": r[2], "lon": r[3]} for r in rows]


# ---------- Encore simulés ----------
@app.get("/scenarios")
def scenarios():
    return [
        {"id": "normal", "name": "Situation normale"},
        {"id": "pointe", "name": "Heure de pointe"},
        {"id": "pluie", "name": "Forte pluie"},
        {"id": "accident", "name": "Accident sur un axe"},
    ]


@app.get("/roads/nearest")
def nearest_road(lat: float, lon: float):
    return {"road_id": "r_0001", "name": "Route de test", "state": "fluide"}


# ---------- Historique (connexion requise) ----------
@app.get("/history")
def history(user_id: str = Depends(current_user_id)):
    with psycopg.connect(DATABASE_URL) as conn:
        rows = conn.execute(
            "select id, center_id, end_lat, end_lon, shortest_m, fastest_s, scenario, created_at "
            "from history where user_id = %s::uuid order by created_at desc limit 50",
            (user_id,),
        ).fetchall()
    return [
        {"id": r[0], "center_id": r[1], "end_lat": r[2], "end_lon": r[3],
         "shortest_m": r[4], "fastest_s": r[5], "scenario": r[6], "created_at": r[7]}
        for r in rows
    ]


@app.post("/history")
def add_history(item: HistoryIn, user_id: str = Depends(current_user_id)):
    with psycopg.connect(DATABASE_URL) as conn:
        new_id = conn.execute(
            "insert into history (user_id, center_id, end_lat, end_lon, shortest_m, fastest_s, scenario) "
            "values (%s::uuid, %s, %s, %s, %s, %s, %s) returning id",
            (user_id, item.center_id, item.end_lat, item.end_lon,
             item.shortest_m, item.fastest_s, item.scenario),
        ).fetchone()[0]
    return {"id": new_id}


# ---------- Favoris (connexion requise) ----------
@app.get("/favorites")
def favorites(user_id: str = Depends(current_user_id)):
    with psycopg.connect(DATABASE_URL) as conn:
        rows = conn.execute(
            "select id, center_id, end_lat, end_lon, label "
            "from favorites where user_id = %s::uuid order by created_at desc",
            (user_id,),
        ).fetchall()
    return [
        {"id": r[0], "center_id": r[1], "end_lat": r[2], "end_lon": r[3], "label": r[4]}
        for r in rows
    ]


@app.post("/favorites")
def add_favorite(item: FavoriteIn, user_id: str = Depends(current_user_id)):
    with psycopg.connect(DATABASE_URL) as conn:
        new_id = conn.execute(
            "insert into favorites (user_id, center_id, end_lat, end_lon, label) "
            "values (%s::uuid, %s, %s, %s, %s) returning id",
            (user_id, item.center_id, item.end_lat, item.end_lon, item.label),
        ).fetchone()[0]
    return {"id": new_id}


@app.delete("/favorites/{favorite_id}")
def delete_favorite(favorite_id: int, user_id: str = Depends(current_user_id)):
    with psycopg.connect(DATABASE_URL) as conn:
        deleted = conn.execute(
            "delete from favorites where id = %s and user_id = %s::uuid returning id",
            (favorite_id, user_id),
        ).fetchone()
    if not deleted:
        raise HTTPException(status_code=404, detail="Favori introuvable")
    return {"deleted": favorite_id}