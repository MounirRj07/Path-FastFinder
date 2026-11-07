
"""
main.py - Point d'entree de l'API Path-FastFinder.

Version minimale (Mounir) : charge le graphe et expose /health.
Emmanuela y ajoutera les routes /route, /places et /admin.
"""

import os
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.routing.alternatives import compute_routes
from app.routing.graph import Graph
from app.routing.snapping import Snapper


@asynccontextmanager
async def lifespan(app: FastAPI):
    t0 = time.perf_counter()
    graph = Graph.load(os.environ.get("GRAPH_PATH", "../data/graph"))
    app.state.graph = graph
    app.state.snapper = Snapper(graph)
    app.state.load_time_s = round(time.perf_counter() - t0, 2)
    print(f"Graphe charge : {graph.n_nodes} noeuds, {graph.n_edges} aretes "
          f"en {app.state.load_time_s} s")

    # Precompilation de Dijkstra (Numba) : sans ca, le premier utilisateur
    # attendrait plusieurs secondes. Le graphe etant fortement connexe,
    # il existe toujours un chemin entre le premier et le dernier noeud.
    t1 = time.perf_counter()
    compute_routes(graph.offsets, graph.targets, graph.lengths, graph.speeds,
                   0, graph.n_nodes - 1, k=1)
    app.state.warmup_time_s = round(time.perf_counter() - t1, 2)
    print(f"Dijkstra precompile en {app.state.warmup_time_s} s")
    yield


app = FastAPI(title="Path-FastFinder API", lifespan=lifespan)

# A restreindre a l'URL du frontend (variable FRONTEND_URL) avant la mise en production
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get("FRONTEND_URL", "*").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health(request: Request):
    """Verifie que le serveur tourne et que le graphe est charge."""
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
