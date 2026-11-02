# Itinéraire Dijkstra

Application web de calcul d'itinéraire qui détermine le **plus court chemin** entre deux points et propose des **chemins alternatifs**, à l'aide d'une implémentation maison de l'**algorithme de Dijkstra**.

Zone couverte : départements du **Littoral** et de l'**Atlantique** (Bénin), à partir des données OpenStreetMap.

> Statut : en développement

---

## Sommaire

- [Fonctionnalités](#fonctionnalités)
- [Stack technique](#stack-technique)
- [Architecture](#architecture)
- [Algorithmes](#algorithmes)
- [Structure du dépôt](#structure-du-dépôt)
- [Prérequis](#prérequis)
- [Installation](#installation)
- [Préparation du graphe routier](#préparation-du-graphe-routier)
- [Lancement](#lancement)
- [API](#api)
- [Équipe et répartition des tâches](#équipe-et-répartition-des-tâches)
- [Feuille de route](#feuille-de-route)
- [Licence et attributions](#licence-et-attributions)

---

## Fonctionnalités

- Choix du départ et de l'arrivée par clic sur la carte ou par recherche de lieu
- Calcul du plus court chemin avec Dijkstra
- Affichage de chemins alternatifs réellement distincts
- Distance et durée estimée pour chaque chemin
- Prise en compte des sens uniques
- Recherche de lieux tolérante aux fautes de frappe
- Statistiques de calcul affichées (temps en ms, nœuds explorés)
- Historique et trajets favoris pour les utilisateurs connectés

---

## Stack technique

| Couche | Technologie | Rôle |
|---|---|---|
| Données | OpenStreetMap | Réseau routier de la zone |
| Prétraitement | osmnx | Conversion d'OSM en graphe orienté exportable |
| Interface | Next.js + TypeScript | Application web |
| Carte | MapLibre GL JS + OpenFreeMap | Affichage fluide de la carte et des tracés |
| API | FastAPI (Python) | Réception des demandes, renvoi des chemins |
| Calcul | NumPy (format CSR) + Numba | Dijkstra compilé, graphe chargé en RAM |
| Accroche au réseau | `scipy.spatial.cKDTree` | Point cliqué → carrefour le plus proche |
| Stockage | PostgreSQL + PostGIS + pg_trgm (Supabase) | Lieux, recherche, utilisateurs, historique |

### Justification des choix

- **Numba** compile notre propre implémentation de Dijkstra en code machine : on garde un algorithme écrit et maîtrisé par nous, avec une vitesse proche du C.
- **Format CSR** (trois tableaux NumPy : `offsets`, `voisins`, `poids`) : représentation compacte et contiguë en mémoire, compatible avec Numba.
- **Graphe en RAM, pas en base** : le calcul d'itinéraire ne passe jamais par PostgreSQL. Interroger la base arête par arête serait des centaines de fois plus lent.
- **MapLibre GL JS** : rendu WebGL fluide, open source, sans quota payant.
- **PostGIS + pg_trgm** : index spatiaux pour les recherches géographiques et recherche approximative par nom de lieu.

---

## Architecture

```
┌──────────────────────────────┐
│  Navigateur                  │
│  Next.js + MapLibre GL JS    │
└──────────────┬───────────────┘
               │ HTTP / JSON
┌──────────────▼───────────────┐
│  API FastAPI                 │
│                              │
│  ┌────────────────────────┐  │
│  │ Graphe CSR (RAM)       │  │
│  │ KD-tree (RAM)          │  │
│  │ Dijkstra (Numba)       │  │
│  └────────────────────────┘  │
└──────────────┬───────────────┘
               │ SQL
┌──────────────▼───────────────┐
│  PostgreSQL + PostGIS        │
│  lieux · utilisateurs ·      │
│  historique                  │
└──────────────────────────────┘

Hors ligne : OpenStreetMap ──osmnx──▶ graphe binaire (data/graph/)
```

Déroulement d'une requête :

1. L'utilisateur choisit un départ et une arrivée.
2. Si besoin, l'API résout le nom du lieu via PostgreSQL.
3. Le KD-tree accroche chaque point au carrefour le plus proche.
4. Dijkstra calcule le plus court chemin, puis les alternatives.
5. L'API renvoie les tracés (coordonnées), distances et durées.
6. MapLibre affiche le plus court chemin en couleur, les alternatives en gris.

---

## Algorithmes

### Dijkstra

Implémentation avec tas binaire, sur graphe orienté pondéré par la longueur des tronçons (ou leur durée de parcours).

- Complexité : O((V + E) log V)
- **Arrêt anticipé** : le calcul s'arrête dès que la destination est atteinte, au lieu d'explorer toute la zone.
- Variante prévue : **Dijkstra bidirectionnel** (recherche simultanée depuis le départ et l'arrivée).

### Chemins alternatifs

Deux méthodes, toutes deux construites sur Dijkstra :

- **Méthode des pénalités** (par défaut) : on calcule le plus court chemin, on augmente le poids de ses arêtes, puis on relance Dijkstra. Produit des alternatives nettement différentes.
- **Algorithme de Yen** (k plus courts chemins) : solution exacte, mais les chemins obtenus sont souvent très proches les uns des autres. Implémenté à des fins de comparaison.

---

## Structure du dépôt

```
.
├── frontend/                # Application Next.js
│   ├── app/
│   ├── components/
│   │   └── Map/             # Composants MapLibre (client uniquement)
│   └── lib/                 # Appels à l'API, types partagés
├── backend/                 # API FastAPI
│   ├── app/
│   │   ├── main.py          # Point d'entrée de l'API
│   │   ├── routes/          # Endpoints
│   │   ├── routing/
│   │   │   ├── graph.py     # Chargement du graphe CSR
│   │   │   ├── dijkstra.py  # Dijkstra (Numba)
│   │   │   ├── alternatives.py  # Pénalités et Yen
│   │   │   └── snapping.py  # KD-tree
│   │   └── db/              # Accès PostgreSQL
│   ├── tests/
│   └── requirements.txt
├── preprocessing/           # Scripts hors ligne
│   ├── build_graph.py       # OSM → graphe CSR
│   └── import_places.py     # OSM → table des lieux
├── data/
│   └── graph/               # Graphe binaire généré (ignoré par git)
├── .env.example
└── README.md
```

---

## Prérequis

- Python 3.11 ou plus
- Node.js 20 ou plus
- Un projet Supabase (ou PostgreSQL 15+ avec PostGIS et pg_trgm)
- Git

---

## Installation

```bash
git clone https://github.com/Powellfgn17/itineraire-dijkstra.git
cd itineraire-dijkstra
```

### Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate        # Windows : .venv\Scripts\activate
pip install -r requirements.txt
```

### Frontend

```bash
cd frontend
npm install
```

### Variables d'environnement

Copier `.env.example` en `.env` puis renseigner les valeurs :

```env
# Backend
DATABASE_URL=postgresql://user:password@host:5432/postgres
GRAPH_PATH=../data/graph

# Frontend
NEXT_PUBLIC_API_URL=http://localhost:8000
NEXT_PUBLIC_MAP_STYLE_URL=https://tiles.openfreemap.org/styles/liberty
```

### Base de données

Activer les extensions dans PostgreSQL (éditeur SQL de Supabase) :

```sql
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
```

---

## Préparation du graphe routier

À exécuter une seule fois, puis à chaque mise à jour des données OSM :

```bash
cd preprocessing
python build_graph.py      # télécharge le réseau routier et génère data/graph/
python import_places.py    # importe les lieux dans PostgreSQL
```

`build_graph.py` :

1. télécharge le réseau routier du Littoral et de l'Atlantique avec osmnx ;
2. simplifie le graphe et conserve les sens uniques ;
3. calcule la longueur et la durée estimée de chaque tronçon ;
4. exporte le graphe au format CSR (`offsets`, `voisins`, `poids`) avec les coordonnées des nœuds.

---

## Lancement

### Backend

```bash
cd backend
uvicorn app.main:app --reload --port 8000
```

Documentation interactive de l'API : http://localhost:8000/docs

### Frontend

```bash
cd frontend
npm run dev
```

Application : http://localhost:3000

### Tests

```bash
cd backend
pytest
```

---

## API

### `GET /route`

Calcule le plus court chemin et les alternatives.

| Paramètre | Type | Description |
|---|---|---|
| `from_lat`, `from_lon` | float | Coordonnées du départ |
| `to_lat`, `to_lon` | float | Coordonnées de l'arrivée |
| `alternatives` | int | Nombre d'alternatives (défaut : 2) |
| `method` | string | `penalty` (défaut) ou `yen` |

Exemple de réponse :

```json
{
  "routes": [
    {
      "rank": 1,
      "distance_m": 5420,
      "duration_s": 780,
      "geometry": [[2.4183, 6.3654], [2.4201, 6.3660]]
    }
  ],
  "stats": {
    "compute_time_ms": 12.4,
    "nodes_explored": 8350
  }
}
```

### `GET /places?q=...`

Recherche de lieux par nom (recherche approximative).

---

## Équipe et répartition des tâches

Chaque membre est **responsable d'un module complet** : il le code, écrit ses tests et documente son fonctionnement. Les charges ont été équilibrées pour que chacun ait un volume de travail comparable.

### Frontend — Elnis & Aliou

| Membre | Module | Tâches |
|---|---|---|
| **Elnis** | Carte et itinéraires | Composant carte MapLibre (rendu client uniquement) · sélection du départ et de l'arrivée par clic, avec marqueurs déplaçables · affichage du plus court chemin en couleur et des alternatives en gris · panneau des résultats (distance, durée, statistiques de calcul) synchronisé avec la carte : survoler ou choisir un chemin dans la liste le met en évidence sur la carte · états de chargement et d'erreur · attribution OpenStreetMap visible · adaptation mobile |
| **Aliou** | Interface, recherche et comptes | Mise en page générale et navigation · client API et types TypeScript partagés (`frontend/lib/`) · barre de recherche de lieux avec autocomplétion (appel à `/places`) · pages de connexion et d'inscription · pages historique et favoris · déploiement du frontend (Vercel) |

### Backend — Mounir, Lambert & Emmanuela

| Membre | Module | Tâches |
|---|---|---|
| **Mounir** | Données et graphe | Prototype Python (osmnx + Dijkstra + folium) avec Lambert · script `build_graph.py` : téléchargement OSM, simplification, sens uniques, longueur et durée des tronçons, export CSR · chargement du graphe en RAM (`graph.py`) · accroche au réseau par KD-tree (`snapping.py`) · conteneurisation (Docker) et déploiement du backend |
| **Lambert** | Algorithmes | Prototype Python avec Mounir · Dijkstra compilé avec Numba, avec arrêt anticipé (`dijkstra.py`) · tests de validation contre le prototype · chemins alternatifs : méthode des pénalités et algorithme de Yen (`alternatives.py`) · Dijkstra bidirectionnel · mesures et comparaison des performances |
| **Emmanuela** | API et base de données | Schéma PostgreSQL/PostGIS et extensions · script `import_places.py` (OSM → table des lieux) · endpoints FastAPI `/route` et `/places` (validation, format de réponse, gestion d'erreurs) · recherche approximative avec pg_trgm · authentification et endpoints historique et favoris · configuration (`.env`, CORS) |

### Points de synchronisation

- **Contrat d'API (semaine 1)** : Emmanuela, Elnis et Aliou fixent ensemble le format exact des requêtes et réponses de `/route` et `/places`. Le frontend peut ensuite avancer avec des données simulées sans attendre le backend.
- **Format du graphe (semaine 1)** : Mounir et Lambert fixent la structure des fichiers CSR (noms des tableaux, types, unité des poids).
- **Intégration** : Lambert fournit à Emmanuela une fonction unique du type `compute_routes(source, target, k, method)`, appelée par l'endpoint `/route`.

### Règles de travail

- Une branche par fonctionnalité (`feature/carte-maplibre`, `feature/dijkstra-numba`, etc.), jamais de commit direct sur `main`.
- Toute pull request est relue par au moins un autre membre avant fusion.
- Une fonctionnalité n'est terminée que si elle est testée et documentée.

---

## Feuille de route

| Étape | Responsable(s) | Statut |
|---|---|---|
| Prototype Python (osmnx + Dijkstra + affichage folium) | Mounir, Lambert | À faire |
| Contrat d'API et format du graphe | Toute l'équipe | À faire |
| Export du graphe au format CSR | Mounir | À faire |
| Dijkstra compilé avec Numba et testé contre le prototype | Lambert | À faire |
| Schéma de base de données et import des lieux | Emmanuela | À faire |
| Endpoints `/route` et `/places` | Emmanuela | À faire |
| Interface carte avec MapLibre et affichage des tracés | Elnis | À faire |
| Recherche de lieux avec autocomplétion | Aliou | À faire |
| Chemins alternatifs (pénalités puis Yen) | Lambert | À faire |
| Panneau des résultats synchronisé avec la carte | Elnis | À faire |
| Comptes utilisateurs, historique et favoris | Aliou (front), Emmanuela (back) | À faire |
| Dijkstra bidirectionnel et comparaison des performances | Lambert | À faire |
| Déploiement | Aliou (front), Mounir (back) | À faire |

---

## Licence et attributions

Code source : licence MIT (voir `LICENSE`).

Données cartographiques : © les contributeurs d'[OpenStreetMap](https://www.openstreetmap.org/copyright), disponibles sous licence ODbL. Cette attribution doit rester visible sur la carte de l'application.

