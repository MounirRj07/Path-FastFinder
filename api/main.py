from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI(title="API itinéraire secours")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

class Point(BaseModel):
    lat: float
    lon: float

class RouteRequest(BaseModel):
    start: Point
    end: Point
    scenario: str | None = None
    road_overrides: dict[str, str] = {}   # identifiant de route -> état

class RouteResult(BaseModel):
    coordinates: list[list[float]]        # [lon, lat]
    distance_m: float
    duration_s: float

class RouteResponse(BaseModel):
    shortest: RouteResult
    fastest: RouteResult
    identical: bool

@app.post("/route", response_model=RouteResponse)
def route(req: RouteRequest):
    # RÉPONSE SIMULÉE : sera remplacée par Dijkstra (Lambert)
    line = [[req.start.lon, req.start.lat], [req.end.lon, req.end.lat]]
    return RouteResponse(
        shortest=RouteResult(coordinates=line, distance_m=3200, duration_s=480),
        fastest=RouteResult(coordinates=line, distance_m=3500, duration_s=420),
        identical=False,
    )

@app.get("/centers")
def centers():
    return [{"id": 1, "name": "Centre de test", "lat": 6.40, "lon": 2.33}]

@app.get("/places")
def places(q: str):
    return [{"id": 1, "name": f"Résultat pour {q}", "lat": 6.40, "lon": 2.33}]

@app.get("/scenarios")
def scenarios():
    return [{"id": "normal", "name": "Situation normale"},
            {"id": "pointe", "name": "Heure de pointe"},
            {"id": "pluie", "name": "Forte pluie"},
            {"id": "accident", "name": "Accident sur un axe"}]

@app.get("/roads/nearest")
def nearest_road(lat: float, lon: float):
    return {"road_id": "r_0001", "name": "Route de test", "state": "fluide"}

@app.get("/history")
def history():
    return []

@app.get("/favorites")
def favorites():
    return []