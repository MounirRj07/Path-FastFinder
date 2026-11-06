# Guide de Mounir — Données, graphe et accroche au réseau

Ce guide explique **ce que fait ta partie**, **pourquoi elle est faite ainsi**, et **ce que tu dois faire, dans l'ordre**, pour la livrer.

Le code de base est déjà écrit et testé (22 tests qui passent). Ton travail consiste à le comprendre, le lancer sur les vraies données, vérifier le résultat, le partager avec l'équipe et déployer le backend.

---

## Sommaire

1. [Ton rôle dans le projet](#1-ton-rôle-dans-le-projet)
2. [Les notions à comprendre](#2-les-notions-à-comprendre)
3. [Les fichiers qui te sont confiés](#3-les-fichiers-qui-te-sont-confiés)
4. [Étape par étape](#4-étape-par-étape)
5. [Ce que tu livres aux autres](#5-ce-que-tu-livres-aux-autres)
6. [Pièges à éviter](#6-pièges-à-éviter)
7. [Planning et liste de contrôle](#7-planning-et-liste-de-contrôle)

---

## 1. Ton rôle dans le projet

Tu es **le premier maillon de la chaîne**. Sans ton travail, personne ne peut tester sur des données réelles.

```
OpenStreetMap ──▶ build_graph.py ──▶ data/graph/ ──▶ graph.py ──▶ Dijkstra (Lambert)
  (Internet)        (toi)          (fichiers)      (toi)
                                                   snapping.py ──▶ API (Emmanuela)
                                                     (toi)          ├─ /route  : clic utilisateur → carrefour
                                                                    └─ /admin  : clic admin → route à pénaliser
```

Tu es responsable de quatre choses :

| # | Livrable | Fichier | Qui l'utilise |
|---|---|---|---|
| 1 | Prototype (avec Lambert) | `preprocessing/prototype.py` | Lambert, pour comparer son Dijkstra |
| 2 | Le graphe de l'Atlantique | `preprocessing/build_graph.py` → `data/graph/` | Toute l'équipe |
| 3 | Chargement et accroche au réseau | `backend/app/routing/graph.py`, `snapping.py` | Lambert, Emmanuela |
| 4 | Déploiement du backend | `backend/Dockerfile` | Toute l'équipe, Aliou (URL de l'API) |

---

## 2. Les notions à comprendre

### 2.1 OpenStreetMap (OSM)

OSM est une carte du monde libre, construite par des bénévoles. Les routes y sont décrites par :

- des **nœuds** (*nodes*) : des points avec une latitude et une longitude ;
- des **voies** (*ways*) : des suites de nœuds formant une rue, avec des **balises** (*tags*) : `highway=primary` (type de route), `name=...`, `oneway=yes` (sens unique), `maxspeed=50`.

Chaque nœud et chaque voie a un **identifiant OSM** unique (`osmid`).

### 2.2 Ce que fait osmnx

`osmnx` télécharge les routes d'une zone et les transforme en **graphe** `networkx` :

- **un nœud du graphe = un carrefour** (ou une extrémité de rue) ;
- **une arête = un tronçon de route entre deux carrefours**.

Avec `simplify=True`, les points intermédiaires d'une rue (les virages) sont fusionnés : un tronçon entre deux carrefours devient **une seule arête**, qui garde son tracé courbe dans l'attribut `geometry`.

Le graphe est **orienté** (`MultiDiGraph`) :

- une route à double sens donne **deux arêtes** : A → B et B → A ;
- une route à sens unique n'en donne **qu'une**.

C'est capital : si tu perds l'orientation, Dijkstra fera prendre des sens interdits.

### 2.3 Pourquoi on n'utilise pas networkx en production

networkx stocke chaque nœud et chaque arête dans des dictionnaires Python. C'est pratique, mais lent et gourmand en mémoire. Pour que Lambert puisse compiler Dijkstra avec Numba, il faut des **tableaux NumPy**. C'est le rôle du format CSR.

### 2.4 Le format CSR (Compressed Sparse Row)

On range toutes les arêtes dans des tableaux, **triées par nœud de départ**. Un tableau `offsets` indique où commencent les arêtes de chaque nœud.

Exemple avec 4 nœuds :

```
Arêtes :  0→1 (110 m)   0→2 (50 m)   1→2 (30 m)   2→3 (80 m)   3→0 (60 m)

           arête :   0     1     2     3     4
targets  =        [  1,    2,    2,    3,    0 ]
lengths  =        [ 110,  50,   30,   80,   60 ]

offsets  = [ 0, 2, 3, 4, 5 ]
             │  │  │  │  └─ fin
             │  │  │  └──── le nœud 3 commence à l'arête 4
             │  │  └─────── le nœud 2 commence à l'arête 3
             │  └────────── le nœud 1 commence à l'arête 2
             └───────────── le nœud 0 commence à l'arête 0
```

Les voisins du nœud `u` sont `targets[offsets[u] : offsets[u+1]]`. Pour le nœud 0 : `targets[0:2] = [1, 2]`.

`offsets` a donc **N + 1** éléments (N = nombre de nœuds). C'est exactement la boucle que Lambert écrira dans Dijkstra :

```python
for e in range(offsets[u], offsets[u + 1]):
    v = targets[e]
    cout = lengths[e]
```

**L'identifiant d'une arête est sa position dans ces tableaux.** C'est cet identifiant que l'admin pénalise et qu'Emmanuela stocke en base.

### 2.5 La renumérotation des nœuds

Les identifiants OSM sont de grands nombres (`8542217731`). Pour utiliser des tableaux, on renumérote les nœuds de **0 à N−1**. On garde la correspondance dans `node_osmids.npy` (la case `i` contient l'id OSM du nœud `i`).

### 2.6 La composante fortement connexe

Le réseau téléchargé contient des morceaux isolés : un parking privé, une impasse coupée par la frontière de la zone, une rue à sens unique sans issue. Si un utilisateur clique dans un de ces morceaux, Dijkstra ne trouve **aucun chemin**.

Une **composante fortement connexe** est un ensemble de nœuds où l'on peut aller de n'importe quel nœud à n'importe quel autre **en respectant les sens uniques**. On ne garde que la plus grande : ainsi, tout trajet a une solution.

Dans `build_graph.py` : `ox.truncate.largest_component(G, strongly=True)`.

### 2.7 Les arêtes parallèles et les boucles

- Deux routes différentes peuvent relier les mêmes carrefours A et B. Le format CSR n'en garde **qu'une : la plus courte** (Dijkstra ne prendrait de toute façon que celle-là).
- Une boucle (A → A, par exemple un rond-point mal découpé) est inutile pour un plus court chemin : on la supprime.

### 2.8 L'accroche au réseau (*snapping*)

L'utilisateur clique n'importe où sur la carte, souvent à côté d'une route. Il faut ramener ce clic sur le graphe :

- **pour l'utilisateur** : au **carrefour le plus proche** (`nearest_node`), qui devient la source ou la cible de Dijkstra ;
- **pour l'administrateur** : au **tronçon le plus proche** (`nearest_edge`), qui est la route à pénaliser.

Comparer le clic à 50 000 nœuds à chaque requête serait lent. Un **KD-tree** (`scipy.spatial.cKDTree`) range les points dans un arbre et trouve le plus proche en quelques microsecondes.

Trois subtilités sont gérées dans `snapping.py` :

1. **Projection en mètres.** Un degré de longitude ne vaut pas un degré de latitude en distance. On convertit (lon, lat) en mètres avant de construire le KD-tree, sinon le « plus proche » serait faux.
2. **Les longues routes droites.** Pour trouver le tronçon le plus proche, on indexe les segments des tracés. Une route droite de 2 km n'a qu'un segment, dont le milieu peut être à 1 km du clic. On découpe donc les segments en morceaux de 25 m maximum.
3. **Les deux sens d'une route.** Quand l'admin clique sur une route à double sens, il faut pénaliser **les deux arêtes** (A → B et B → A), sinon les voitures continueraient à passer dans l'autre sens. `select_road` s'en charge.

Un clic à plus de **500 m** de toute route lève `OutOfZoneError` : Emmanuela la transforme en message « hors zone ».

---

## 3. Les fichiers qui te sont confiés

```
preprocessing/
├── requirements.txt      # osmnx, numpy, folium
├── prototype.py          # tâche 1 : prototype sur une petite zone
└── build_graph.py        # tâche 2 : OSM → data/graph/

backend/
├── Dockerfile            # tâche 4 : déploiement
├── app/routing/
│   ├── graph.py          # tâche 3 : chargement du graphe
│   └── snapping.py       # tâche 3 : accroche au réseau
└── tests/
    ├── conftest.py       # petit graphe artificiel pour les tests
    ├── test_graph.py
    └── test_snapping.py
```

### 3.1 `build_graph.py`, fonction par fonction

| Fonction | Ce qu'elle fait |
|---|---|
| `download(place)` | Récupère la frontière du département, télécharge les routes, garde la composante fortement connexe, ajoute les vitesses |
| `to_arrays(G)` | Convertit le graphe osmnx en tableaux CSR. **Fonction pure, testée sans Internet** |
| `save(...)` | Écrit les fichiers `.npy`, `.json` et `boundary.geojson` dans `data/graph/` |
| `_speed(data)` | Vitesse de l'arête : celle d'OSM si elle existe, sinon une valeur par défaut selon le type de route |
| `_first`, `_name` | Après simplification, osmnx stocke parfois une **liste** (plusieurs rues fusionnées) : on la ramène à une valeur |
| `_edge_coords` | Tracé de l'arête, en s'assurant qu'il va bien du nœud de départ au nœud d'arrivée |

Les vitesses par défaut sont dans `DEFAULT_SPEEDS_KPH` en haut du fichier. **Ajuste-les à la réalité de la zone** (par exemple, la vitesse réelle sur une route principale d'Abomey-Calavi aux heures de pointe). Elles servent uniquement à estimer la durée affichée.

### 3.2 Les fichiers produits dans `data/graph/`

| Fichier | Taille | Contenu |
|---|---|---|
| `offsets.npy` | N+1 | Début des arêtes de chaque nœud |
| `sources.npy` | E | Nœud de départ de chaque arête |
| `targets.npy` | E | Nœud d'arrivée de chaque arête |
| `lengths.npy` | E | Longueur en mètres (float64) |
| `speeds.npy` | E | Vitesse en km/h |
| `way_ids.npy` | E | Id OSM de la rue (pour « toute la rue ») |
| `name_ids.npy` + `names.json` | E | Nom de la rue |
| `highway_ids.npy` + `highways.json` | E | Type de route |
| `node_coords.npy` | N × 2 | (longitude, latitude) de chaque nœud |
| `node_osmids.npy` | N | Id OSM d'origine |
| `geom_offsets.npy` + `geom_coords.npy` | E+1, P × 2 | Tracé de chaque arête (même principe que le CSR) |
| `boundary.geojson` | — | Frontière du département (pour la carte et le contrôle « hors zone ») |
| `meta.json` | — | Version du format, date, nombre de nœuds et d'arêtes, emprise |

### 3.3 `graph.py`

La classe `Graph` charge tous ces fichiers **une seule fois** et vérifie leur cohérence (`_validate`). Si un fichier manque ou est corrompu, le serveur refuse de démarrer avec un message clair, au lieu de renvoyer des chemins faux.

Méthodes utiles pour l'équipe :

| Méthode | Utilisée par | Rôle |
|---|---|---|
| `offsets`, `targets`, `lengths` | Lambert | Les tableaux donnés à Dijkstra |
| `out_edges(u)` | Lambert (prototype) | Arêtes sortant du nœud `u` |
| `find_edge(u, v)` | Lambert | Arête u → v (utile pour reconstruire un chemin à partir des nœuds) |
| `path_geometry(edge_ids)` | Emmanuela | Tracé complet d'un chemin, prêt pour le JSON |
| `path_stats(edge_ids)` | Emmanuela | Distance (m) et durée (s) d'un chemin |
| `edge_name(e)` | Emmanuela, Aliou | Nom de la rue (liste des pénalités) |
| `reverse_edge(e)`, `edges_of_way(w)` | `snapping.py` | Sens inverse, toute la rue |

### 3.4 `snapping.py`

| Méthode | Utilisée par | Rôle |
|---|---|---|
| `Snapper(graph)` | Emmanuela (au démarrage) | Construit les deux KD-trees (≈ 0,5 s) |
| `nearest_node(lat, lon)` | `/route` | Carrefour le plus proche → `(nœud, distance_m)` |
| `nearest_edge(lat, lon)` | `/admin/edges/nearest` | Tronçon le plus proche → `(arête, distance_m)` |
| `select_road(lat, lon, whole_way)` | `/admin/edges/nearest` | Liste des arêtes à pénaliser (les deux sens, ou toute la rue) |

Attention à l'ordre des paramètres : **`(lat, lon)`** dans ces fonctions, alors que les coordonnées stockées et le GeoJSON utilisent **`(lon, lat)`**. Préviens Emmanuela.

### 3.5 Performances mesurées

Sur un graphe artificiel de 53 000 nœuds et 210 000 arêtes (plus gros que l'Atlantique) :

| Opération | Temps |
|---|---|
| `to_arrays` | 1 s |
| `Graph.load` | 0,05 s |
| `Snapper(graph)` | 0,5 s |
| `nearest_edge` | 0,04 ms par appel |

---

## 4. Étape par étape

Les commandes sont pour **PowerShell (Windows)**. Sur Linux/macOS, remplace `.venv\Scripts\activate` par `source .venv/bin/activate`.

### Étape 0 — Préparer ton environnement (J1)

```powershell
cd D:\Path-FastFinder\Path-FastFinder        # adapte le chemin
git checkout main
git pull
git checkout -b feature/graph-pipeline

python -m venv .venv
.venv\Scripts\activate
pip install -r preprocessing\requirements.txt
pip install scipy pytest
```

Copie les fichiers de ce paquet aux mêmes emplacements dans le dépôt.

Vérifie que tout fonctionne **avant** de toucher aux vraies données :

```powershell
cd backend
python -m pytest -q
# Attendu : 22 passed
cd ..
```

Si un test échoue, ne continue pas : c'est ton environnement qui pose problème (version de Python ou d'une bibliothèque).

### Étape 1 — Prototype avec Lambert (J1–J2)

```powershell
cd preprocessing
python prototype.py
```

Ouvre `prototype.html` dans ton navigateur : tu dois voir un chemin bleu sur une carte d'Abomey-Calavi.

À faire **avec Lambert** :

1. Regarder ensemble l'exemple d'arête affiché dans le terminal (`length`, `highway`, `oneway`, `osmid`...). C'est la matière première de `build_graph.py`.
2. Lambert écrit son Dijkstra en Python pur et vérifie qu'il trouve la même distance que `nx.dijkstra_path_length`.
3. **Figer ensemble le format du graphe** (section 3.2). À partir de là, ni toi ni lui ne le changez sans prévenir l'autre.

### Étape 2 — Générer le vrai graphe (J3–J4)

```powershell
cd preprocessing
python build_graph.py --geojson
```

La première exécution prend plusieurs minutes (téléchargement). Les suivantes sont rapides grâce au dossier `cache/`.

**Contrôle 1 — la bonne zone.** Le script affiche :

```
Trouvé : Atlantique, Bénin
Emprise (lon/lat) : [...]
```

Le nom doit être le **département de l'Atlantique**. L'emprise doit couvrir à peu près les longitudes 1,9 à 2,5 et les latitudes 6,3 à 7,0. Si ce n'est pas le cas :

1. va sur [openstreetmap.org](https://www.openstreetmap.org), cherche « Atlantique Bénin » ;
2. ouvre le résultat de type **relation administrative** (frontière du département), note son numéro ;
3. relance avec `python build_graph.py --place R<numéro> --geojson`.

**Contrôle 2 — les nombres.** Le script termine par `Terminé en ... : X nœuds, Y arêtes`. Note-les. Si la ligne « Composante principale » montre que plus de 20 % des nœuds ont été retirés, signale-le : la frontière coupe probablement mal le réseau.

**Contrôle 3 — visuel.** Ouvre `data/graph/edges.geojson` dans [geojson.io](https://geojson.io) (s'il n'est pas trop gros) ou dans **QGIS** (gratuit). Vérifie :

- que les routes couvrent bien tout le département ;
- que les grands axes (RNIE 1, RNIE 2) sont présents et continus ;
- les sens uniques sur quelques rues que tu connais.

**Contrôle 4 — le chargement.**

```powershell
cd ..\backend
python -c "from app.routing.graph import Graph; from app.routing.snapping import Snapper; g = Graph.load('../data/graph'); s = Snapper(g); print(g.meta); print(s.nearest_node(6.4183, 2.3410))"
```

Si `Graph.load` lève une `GraphFormatError`, lis le message : il indique quel contrôle a échoué.

### Étape 3 — Partager le graphe avec l'équipe (J4)

Le dossier `data/graph/` est dans le `.gitignore` : **il ne doit pas aller dans Git** (fichiers binaires lourds, regénérables). On le partage via une **release GitHub** :

```powershell
Compress-Archive -Path ..\data\graph\* -DestinationPath graph-v1.zip -Force
```

Puis sur GitHub : **Releases → Draft a new release** → tag `graph-v1` → glisse `graph-v1.zip` → **Publish**.

`edges.geojson` est optionnel : s'il rend le zip trop lourd, regénère sans `--geojson` avant de compresser.

Envoie à l'équipe ce message :

> Le graphe est prêt : release `graph-v1`. Téléchargez `graph-v1.zip` et décompressez-le dans `data/graph/`. X nœuds, Y arêtes. Format décrit dans le README.

**Si le dépôt est privé**, le lien de téléchargement demande une authentification. Les membres le téléchargent depuis leur navigateur connecté ; pour le déploiement, voir l'étape 5.

### Étape 4 — Intégrer le chargement au serveur (J5–J7, avec Emmanuela)

Le fichier `main.py` appartient à Emmanuela, mais le chargement du graphe est ton code. Donne-lui ce bloc :

```python
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI

from app.routing.graph import Graph
from app.routing.snapping import Snapper


@asynccontextmanager
async def lifespan(app: FastAPI):
    graph = Graph.load(os.environ.get("GRAPH_PATH", "../data/graph"))
    app.state.graph = graph
    app.state.snapper = Snapper(graph)
    print(f"Graphe chargé : {graph.n_nodes} nœuds, {graph.n_edges} arêtes")
    yield


app = FastAPI(lifespan=lifespan)
```

Dans un endpoint, on y accède par `request.app.state.graph` et `request.app.state.snapper`.

Contrôle : lance `uvicorn app.main:app --reload` et vérifie le message « Graphe chargé » au démarrage.

Ouvre ta **pull request** `feature/graph-pipeline` vers `main` et demande une relecture à Lambert.

### Étape 5 — Déployer le backend (J8–J10)

Le `Dockerfile` installe les dépendances, copie le code et **télécharge le graphe depuis la release** pendant la construction.

**Test en local** (nécessite Docker Desktop) :

```powershell
docker build -t path-fastfinder-api --build-arg GRAPH_URL=https://github.com/Mounir07-yo/Path-FastFinder/releases/download/graph-v1/graph-v1.zip backend
docker run -p 8000:8000 --env-file .env path-fastfinder-api
```

Ouvre http://localhost:8000/docs.

**Mise en ligne sur Render** (gratuit) :

1. [render.com](https://render.com) → **New → Web Service** → connecter le dépôt GitHub.
2. Runtime : **Docker**, *Root Directory* : `backend`.
3. Variables d'environnement : `DATABASE_URL`, `SUPABASE_JWT_SECRET` (demande-les à Emmanuela), et `GRAPH_URL` comme *build argument*.
4. Déployer, puis tester `https://<ton-service>.onrender.com/docs`.
5. Donner l'URL à Aliou pour `NEXT_PUBLIC_API_URL`, et à Emmanuela pour la configuration CORS.

Points d'attention :

- **Un seul processus** (`--workers 1`, déjà dans le Dockerfile) : les pénalités sont gardées en mémoire dans le processus. Avec plusieurs processus, chacun aurait sa propre copie et l'admin verrait des résultats incohérents.
- **Mémoire** : le plan gratuit de Render offre 512 Mo. Mesure la consommation réelle (onglet *Metrics*). Si ça déborde, passe à Railway ou à une petite VM.
- **Mise en veille** : le plan gratuit de Render endort le service après 15 minutes sans requête, et le réveil prend environ une minute. Réveille-le avant la démonstration.
- **Dépôt privé** : le `curl` du Dockerfile ne pourra pas télécharger la release. Soit le dépôt devient public, soit on héberge le zip ailleurs (Google Drive avec lien direct, Supabase Storage).

---

## 5. Ce que tu livres aux autres

| Jour | À qui | Quoi |
|---|---|---|
| J2 | Lambert | Format du graphe figé, prototype fonctionnel |
| J4 | Toute l'équipe | Release `graph-v1` + nombre de nœuds et d'arêtes |
| J5 | Emmanuela | Bloc `lifespan`, rappel de l'ordre `(lat, lon)`, exception `OutOfZoneError` |
| J7 | Toute l'équipe | Pull request fusionnée dans `main` |
| J10 | Aliou, Emmanuela | URL publique de l'API |

---

## 6. Pièges à éviter

| Piège | Conséquence | Comment l'éviter |
|---|---|---|
| Convertir le graphe en non orienté | Dijkstra fait prendre des sens interdits | Ne jamais appeler `to_undirected()` ; garder le `MultiDiGraph` |
| Inverser lat et lon | Points accrochés à l'autre bout du pays, ou « hors zone » partout | Stockage en `(lon, lat)`, fonctions de `snapping.py` en `(lat, lon)` |
| Regénérer le graphe sans prévenir | Les identifiants d'arêtes changent, les pénalités pointent sur les mauvaises routes | Toute nouvelle version = nouvelle release (`graph-v2`) + message à Emmanuela, qui réassocie les pénalités par `way_id` |
| Commiter `data/graph/` ou `cache/` | Dépôt lourd et conflits | Ils sont dans le `.gitignore` ; vérifier avec `git status` avant chaque commit |
| Garder les composantes isolées | « Aucun chemin trouvé » sur certains clics | `largest_component(strongly=True)`, déjà dans le script |
| Modifier `lengths` pour les pénalités | Distances affichées fausses | Les pénalités sont un tableau à part (`penalties.py`, Emmanuela) ; `lengths` ne change jamais |
| Lancer plusieurs processus uvicorn | Pénalités incohérentes | `--workers 1` |

---

## 7. Planning et liste de contrôle

| Jours | Tâche | Terminé quand |
|---|---|---|
| J1 | Environnement prêt | `pytest` affiche 22 passed |
| J1–J2 | Prototype avec Lambert | `prototype.html` affiche un chemin, format figé |
| J3–J4 | Graphe de l'Atlantique | 4 contrôles de l'étape 2 validés |
| J4 | Partage | Release `graph-v1` publiée, équipe prévenue |
| J5–J7 | Intégration | Le serveur démarre avec « Graphe chargé », PR fusionnée |
| J8–J10 | Déploiement | `/docs` accessible en ligne, URL transmise |
| J11–J14 | Aide à l'intégration | Disponible pour les bugs liés au graphe et à l'accroche |

### Questions à te poser pour valider ta partie

- [ ] Un clic au milieu d'Abomey-Calavi est accroché à un carrefour à moins de 100 m.
- [ ] Un clic dans l'océan ou au Togo renvoie « hors zone ».
- [ ] Un clic de l'admin sur une rue à double sens sélectionne bien les deux arêtes.
- [ ] Une rue à sens unique connue n'a qu'une arête dans le bon sens.
- [ ] Le graphe se charge en moins de 2 secondes au démarrage du serveur.
- [ ] Aucun fichier de `data/` n'est suivi par Git.
