"""
prototype.py — Prototype rapide (jours 1-2, avec Lambert).

Télécharge une PETITE zone, calcule un plus court chemin avec le Dijkstra de
networkx et l'affiche sur une carte HTML. Sert à :
  1. vérifier que osmnx fonctionne sur ta machine ;
  2. voir à quoi ressemblent les données OSM de la zone ;
  3. fournir à Lambert des résultats de référence pour tester son Dijkstra.

Utilisation :
    python prototype.py
    -> ouvre prototype.html dans le navigateur
"""

import networkx as nx
import osmnx as ox

ox.settings.use_cache = True

# Petite zone pour aller vite : 2 km autour du campus d'Abomey-Calavi
CENTER = (6.4183, 2.3410)          # (lat, lon)
G = ox.graph_from_point(CENTER, dist=2000, network_type="drive")
G = ox.add_edge_speeds(G)
print(f"{G.number_of_nodes()} nœuds, {G.number_of_edges()} arêtes")

# Regarder les attributs d'une arête : c'est ce que build_graph.py exploite
u, v, data = next(iter(G.edges(data=True)))
print("Exemple d'arête :", {k: val for k, val in data.items() if k != "geometry"})

# Deux points de la zone
orig = ox.distance.nearest_nodes(G, X=2.3330, Y=6.4120)
dest = ox.distance.nearest_nodes(G, X=2.3500, Y=6.4250)

path = nx.dijkstra_path(G, orig, dest, weight="length")
length = nx.dijkstra_path_length(G, orig, dest, weight="length")
print(f"Plus court chemin : {len(path)} nœuds, {length:.0f} m")

# Carte interactive (nécessite folium : pip install folium)
import folium  # noqa: E402

m = folium.Map(location=CENTER, zoom_start=14)
coords = [(G.nodes[n]["y"], G.nodes[n]["x"]) for n in path]
folium.PolyLine(coords, weight=6, color="blue").add_to(m)
folium.Marker(coords[0], tooltip="Départ").add_to(m)
folium.Marker(coords[-1], tooltip="Arrivée").add_to(m)
m.save("prototype.html")
print("Carte enregistrée : prototype.html")
