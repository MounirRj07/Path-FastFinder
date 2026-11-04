# Path-FastFinder

Application web de calcul d'itinéraire qui détermine le **plus court chemin** entre deux points et propose des **chemins alternatifs**, à l'aide d'une implémentation maison de l'**algorithme de Dijkstra** et d'un système de **pénalités**.

Un **espace administrateur** permet d'ajouter ou de retirer des pénalités sur les routes (travaux, embouteillages, inondation, route fermée). Les itinéraires calculés en tiennent compte immédiatement.

Zone couverte : départements du **Littoral** et de l'**Atlantique** (Bénin), à partir des données OpenStreetMap.

> Statut : en développement

---

## Sommaire

- [Fonctionnalités](#fonctionnalités)
- [Stack technique](#stack-technique)
- [Architecture](#architecture)
- [Algorithmes](#algorithmes)
- [Modèle de données](#modèle-de-données)
- [API](#api)
- [Structure du dépôt](#structure-du-dépôt)
- [Prérequis](#prérequis)
- [Installation](#installation)
- [Préparation du graphe routier](#préparation-du-graphe-routier)
- [Lancement](#lancement)
- [Équipe et répartition des tâches](#équipe-et-répartition-des-tâches)
- [Planning sur deux semaines](#planning-sur-deux-semaines)
- [Règles de travail](#règles-de-travail)
- [Licence et attributions](#licence-et-attributions)

---

## Fonctionnalités

### Interface utilisateur (publique, sans compte)

- Choix du départ et de l'arrivée par clic sur la carte ou par recherche de lieu
- Calcul du plus court chemin avec Dijkstra
- Affichage de 2 chemins alternatifs obtenus par la méthode des pénalités
- Distance et durée estimée pour chaque chemin
- Signalement visuel des tronçons pénalisés par l'administrateur (travaux, bouchon, etc.)
- Prise en compte des sens uniques
- Recherche de lieux tolérante aux fautes de frappe

### Espace administrateur (connexion obligatoire)

- Connexion sécurisée réservée aux administrateurs
- Sélection d'une route en cliquant sur la carte (un tronçon ou toute la rue)
- Ajout d'une pénalité : niveau (léger, moyen, fort, route fermée), motif, date de début et de fin
- Retrait ou modification d'une pénalité existante
- Liste et carte de toutes les pénalités actives
- Prise en compte immédiate par le moteur de calcul, sans redémarrage du serveur

---

## Stack technique

| Couche | Technologie | Rôle |
|---|---|---|
| Données | OpenStreetMap | Réseau routier de la zone |
| Prétraitement | osmnx | Conversion d'OSM en graphe orienté exportable |
| Interface | Next.js + TypeScript | Pages utilisateur et administrateur |
| Carte | MapLibre GL JS + OpenFreeMap | Affichage fluide de la carte et des tracés |
| API | FastAPI (Python) | Calcul des itinéraires, gestion des pénalités |
| Calcul | NumPy (format CSR) + Numba | Dijkstra compilé, graphe chargé en RAM |
| Accroche au réseau | `scipy.spatial.cKDTree` | Point cliqué → carrefour ou tronçon le plus proche |
| Stockage | PostgreSQL + PostGIS + pg_trgm (Supabase) | Lieux, pénalités, administrateurs |
| Authentification | Supabase Auth | Connexion des administrateurs (jetons JWT) |

### Justification des choix

- **Numba** compile notre propre implémentation de Dijkstra en code machine : on garde un algorithme écrit et maîtrisé par nous, avec une vitesse proche du C.
- **Format CSR** (tableaux NumPy `offsets`, `voisins`, `longueurs`) : représentation compacte et contiguë en mémoire, compatible avec Numba.
- **Graphe en RAM, pas en base** : le calcul d'itinéraire ne passe jamais par PostgreSQL. Interroger la base arête par arête serait des centaines de fois plus lent.
- **Pénalités stockées en base, appliquées en RAM** : PostgreSQL garde l'historique et survit aux redémarrages ; un tableau NumPy de facteurs en mémoire permet au moteur de les appliquer sans coût.
- **Supabase Auth** : gère les mots de passe et les jetons de façon sécurisée, on n'écrit pas notre propre système de connexion.
- **Pas de compte pour les utilisateurs** : seul l'administrateur se connecte. C'est un choix volontaire pour tenir le délai de deux semaines.

---

## Architecture

```
┌──────────────────────────────┐   ┌──────────────────────────────┐
│  Interface utilisateur       │   │  Espace administrateur       │
│  /  (Next.js + MapLibre)     │   │  /admin (Next.js + MapLibre) │
└──────────────┬───────────────┘   └──────────────┬───────────────┘
               │ HTTP / JSON                      │ HTTP / JSON + JWT
┌──────────────▼──────────────────────────────────▼───────────────┐
│  API FastAPI                                                    │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │ Graphe CSR (RAM) · facteurs de pénalité (RAM) · KD-tree  │   │
│  │ Dijkstra (Numba) · méthode des pénalités                 │   │
│  └──────────────────────────────────────────────────────────┘   │
└──────────────┬──────────────────────────────────────────────────┘
               │ SQL
┌──────────────▼───────────────┐
│  PostgreSQL + PostGIS        │
│  lieux · pénalités · admins  │
└──────────────────────────────┘

Hors ligne : OpenStreetMap ──osmnx──▶ graphe binaire (data/graph/)
```

### Déroulement d'une recherche d'itinéraire

1. L'utilisateur choisit un départ et une arrivée.
2. Le KD-tree accroche chaque point au carrefour le plus proche.
3. Dijkstra calcule le plus court chemin avec les pénalités de l'administrateur déjà appliquées.
4. La méthode des pénalités relance Dijkstra pour produire 2 alternatives.
5. L'API renvoie les tracés, distances, durées et tronçons pénalisés.
6. MapLibre affiche le meilleur chemin en couleur, les alternatives en gris, les tronçons pénalisés en orange (fermés en rouge).

### Déroulement de l'ajout d'une pénalité

1. L'administrateur clique sur une route : l'API renvoie le tronçon le plus proche (et sa rue entière si demandé).
2. Il choisit le niveau, le motif et les dates, puis valide.
3. L'API enregistre la pénalité dans PostgreSQL, puis met à jour le tableau des facteurs en RAM.
4. La recherche d'itinéraire suivante en tient compte.

---

## Algorithmes

### Dijkstra

Implémentation avec tas binaire, sur graphe orienté. Le coût d'une arête est :

```
coût(e) = longueur(e) × facteur_admin(e) × facteur_alternative(e)
```

- Complexité : O((V + E) log V)
- **Arrêt anticipé** : le calcul s'arrête dès que la destination est figée.
- Une arête avec un facteur infini (route fermée) n'est jamais empruntée.

### Pénalités de l'administrateur (persistantes)

Chaque niveau correspond à un facteur multiplicatif sur le coût de l'arête :

| Niveau | Facteur | Exemple |
|---|---|---|
| Léger | × 1,5 | Route dégradée |
| Moyen | × 3 | Embouteillage fréquent |
| Fort | × 10 | Travaux, chaussée inondée |
| Fermée | ∞ | Route coupée |

Si plusieurs pénalités actives touchent la même arête, on garde le **facteur le plus élevé** (on ne les multiplie pas). Une pénalité n'est active qu'entre sa date de début et sa date de fin.

### Méthode des pénalités (chemins alternatifs)

1. Calculer le plus court chemin P1 avec Dijkstra.
2. Copier le tableau des coûts, multiplier par **1,4** le coût de chaque arête de P1.
3. Relancer Dijkstra : on obtient P2, qui évite au maximum P1.
4. Répéter une fois pour obtenir P3 (en pénalisant P1 et P2).
5. Écarter une alternative si plus de **70 %** de sa longueur est commune avec un chemin déjà retenu, ou si elle est plus de **1,5 fois** plus longue que P1.

Ces pénalités sont **temporaires** : elles n'existent que pendant le calcul d'une requête, sur une copie du tableau des coûts. Elles ne modifient jamais les pénalités de l'administrateur.

---

## Modèle de données

### Fichiers du graphe (`data/graph/`, générés par `build_graph.py`)

| Fichier | Contenu |
|---|---|
| `offsets.npy` | Début des voisins de chaque nœud (format CSR) |
| `targets.npy` | Nœud d'arrivée de chaque arête |
| `lengths.npy` | Longueur de chaque arête (m) |
| `speeds.npy` | Vitesse estimée de chaque arête (km/h), pour la durée |
| `way_ids.npy` | Identifiant OSM de la rue de chaque arête |
| `node_coords.npy` | Longitude et latitude de chaque nœud |
| `edges.geojson` | Géométrie et nom de chaque arête (affichage, sélection admin) |

L'**identifiant d'une arête** est son indice dans ces tableaux. Il est stable tant que le graphe n'est pas regénéré.

### Tables PostgreSQL

```sql
-- Lieux recherchables
places (id, name, category, geom geography(Point))

-- Pénalités posées par l'administrateur
penalties (
  id, edge_ids int[], way_id bigint, level text, factor real,
  reason text, starts_at timestamptz, ends_at timestamptz,
  created_by uuid, created_at timestamptz, deleted_at timestamptz
)

-- Rôles des comptes Supabase Auth
profiles (user_id uuid, role text)   -- role = 'admin'
```

Une pénalité retirée n'est pas effacée : on remplit `deleted_at`, ce qui garde l'historique.

---

## API

### Routes publiques

**`GET /route`** : plus court chemin et alternatives.

| Paramètre | Type | Description |
|---|---|---|
| `from_lat`, `from_lon` | float | Coordonnées du départ |
| `to_lat`, `to_lon` | float | Coordonnées de l'arrivée |
| `alternatives` | int | Nombre d'alternatives, 0 à 2 (défaut : 2) |

```json
{
  "routes": [
    {
      "rank": 1,
      "distance_m": 5420,
      "duration_s": 780,
      "geometry": [[2.4183, 6.3654], [2.4201, 6.3660]],
      "penalized_segments": [
        { "level": "fort", "reason": "Travaux", "geometry": [[2.4190, 6.3657], [2.4195, 6.3659]] }
      ]
    }
  ],
  "stats": { "compute_time_ms": 18.2, "nodes_explored": 8350 }
}
```

**`GET /places?q=...`** : recherche de lieux par nom (approximative).

**`GET /penalties/active`** : pénalités actives (pour les afficher sur la carte publique).

### Routes administrateur (en-tête `Authorization: Bearer <jwt>` obligatoire)

| Méthode | Route | Rôle |
|---|---|---|
| `GET` | `/admin/edges/nearest?lat=&lon=&whole_way=` | Tronçon (ou rue entière) le plus proche d'un clic |
| `GET` | `/admin/penalties` | Liste des pénalités (actives, à venir, passées) |
| `POST` | `/admin/penalties` | Ajouter une pénalité |
| `PATCH` | `/admin/penalties/{id}` | Modifier une pénalité |
| `DELETE` | `/admin/penalties/{id}` | Retirer une pénalité |

Corps de `POST /admin/penalties` :

```json
{
  "edge_ids": [10432, 10433],
  "level": "fort",
  "reason": "Travaux de voirie",
  "starts_at": "2026-11-10T00:00:00Z",
  "ends_at": "2026-11-20T00:00:00Z"
}
```

---

## Structure du dépôt

```
.
├── frontend/
│   ├── app/
│   │   ├── page.tsx              # Interface utilisateur
│   │   └── admin/
│   │       ├── login/page.tsx    # Connexion administrateur
│   │       └── page.tsx          # Tableau de bord des pénalités
│   ├── components/
│   │   ├── map/                  # Carte partagée (MapLibre, client uniquement)
│   │   ├── user/                 # Recherche, panneau des résultats
│   │   └── admin/                # Formulaire et liste des pénalités
│   └── lib/
│       ├── api.ts                # Client API
│       ├── types.ts              # Types partagés
│       └── supabase.ts           # Client Supabase Auth
├── backend/
│   ├── app/
│   │   ├── main.py               # Point d'entrée, chargement au démarrage
│   │   ├── auth.py               # Vérification du JWT et du rôle admin
│   │   ├── routes/
│   │   │   ├── route.py          # /route
│   │   │   ├── places.py         # /places
│   │   │   └── admin.py          # /admin/*
│   │   ├── routing/
│   │   │   ├── graph.py          # Chargement du graphe CSR
│   │   │   ├── dijkstra.py       # Dijkstra (Numba)
│   │   │   ├── alternatives.py   # Méthode des pénalités
│   │   │   ├── penalties.py      # Facteurs de pénalité en RAM
│   │   │   └── snapping.py       # KD-tree (nœuds et arêtes)
│   │   └── db/                   # Accès PostgreSQL
│   ├── tests/
│   └── requirements.txt
├── preprocessing/
│   ├── build_graph.py            # OSM → graphe CSR
│   └── import_places.py          # OSM → table des lieux
├── data/
│   └── graph/                    # Graphe généré (ignoré par git)
├── .env.example
├── .gitignore
├── LICENSE
└── README.md
```

---

## Prérequis

- Python 3.11 ou plus
- Node.js 20 ou plus
- Un projet Supabase (PostgreSQL avec PostGIS et pg_trgm, et Supabase Auth)
- Git

---

## Installation

```bash
git clone https://github.com/Mounir07-yo/Path-FastFinder.git
cd Path-FastFinder
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
SUPABASE_JWT_SECRET=...

# Frontend
NEXT_PUBLIC_API_URL=http://localhost:8000
NEXT_PUBLIC_MAP_STYLE_URL=https://tiles.openfreemap.org/styles/liberty
NEXT_PUBLIC_SUPABASE_URL=https://xxxx.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=...
```

### Base de données

```sql
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
```

Puis exécuter les scripts de `backend/app/db/schema.sql`.

### Créer un administrateur

1. Créer le compte dans Supabase : **Authentication → Users → Add user**.
2. Lui donner le rôle : `INSERT INTO profiles (user_id, role) VALUES ('<uuid>', 'admin');`

---

## Préparation du graphe routier

```bash
cd preprocessing
python build_graph.py      # génère data/graph/
python import_places.py    # importe les lieux dans PostgreSQL
```

Attention : regénérer le graphe change les identifiants des arêtes. Les pénalités existantes sont alors réassociées grâce à leur `way_id` (identifiant OSM de la rue).

---

## Lancement

```bash
# Backend (un seul processus : les pénalités en RAM ne sont pas partagées entre processus)
cd backend
uvicorn app.main:app --reload --port 8000

# Frontend
cd frontend
npm run dev
```

- Interface utilisateur : http://localhost:3000
- Espace administrateur : http://localhost:3000/admin
- Documentation de l'API : http://localhost:8000/docs

Tests : `cd backend && pytest`

---

## Équipe et répartition des tâches

Chaque membre est **responsable d'un module complet** : il le code, écrit ses tests et le documente. Les charges ont été équilibrées pour un volume de travail comparable.

| Membre | Équipe | Module |
|---|---|---|
| **Elnis** | Frontend | Interface utilisateur |
| **Aliou** | Frontend | Espace administrateur |
| **Mounir** | Backend | Données, graphe et accroche au réseau |
| **Lambert** | Backend | Algorithmes : Dijkstra et pénalités |
| **Emmanuela** | Backend | API, base de données et sécurité |

---

### Elnis — Interface utilisateur

**Objectif :** la page publique où l'utilisateur trouve son itinéraire.

**Tâches et méthode :**

1. **Composant carte partagé** (`components/map/`)
   - Créer un composant `MapView` qui initialise MapLibre avec `NEXT_PUBLIC_MAP_STYLE_URL`, centré sur Cotonou (`[2.42, 6.37]`, zoom 12).
   - Le charger avec `dynamic(() => import(...), { ssr: false })` : MapLibre ne fonctionne pas côté serveur.
   - Ce composant est aussi utilisé par Aliou : le livrer **en premier** (jour 3).
2. **Choix du départ et de l'arrivée**
   - Premier clic = départ, second clic = arrivée, avec deux `maplibregl.Marker` déplaçables (`draggable: true`).
   - Sur l'événement `dragend`, relancer le calcul.
3. **Barre de recherche de lieux** (`components/user/SearchBox.tsx`)
   - Appeler `/places?q=` à chaque frappe, avec un délai de 300 ms (debounce) pour ne pas saturer l'API.
   - Afficher une liste de suggestions ; un choix place le marqueur et recentre la carte (`map.flyTo`).
4. **Affichage des itinéraires**
   - Convertir chaque `geometry` en GeoJSON `LineString`, l'ajouter comme source, et deux couches `line` : le meilleur chemin en bleu (épaisseur 6), les alternatives en gris (épaisseur 4, dessous).
   - Ajouter une couche pour `penalized_segments` : orange, rouge si `fermée`, avec une infobulle (`maplibregl.Popup`) affichant le motif.
5. **Panneau des résultats** (`components/user/ResultsPanel.tsx`)
   - Une carte par chemin : distance (km), durée (min), nombre de tronçons pénalisés.
   - Cliquer sur un chemin le met au premier plan sur la carte.
6. **États et finitions** : chargement pendant le calcul, message clair si aucun chemin n'existe ou si le point est hors zone, attribution OpenStreetMap visible, mise en page mobile.

**Dépend de :** contrat d'API (jour 2). Travailler avec des données simulées (`mocks/route.json`) jusqu'à ce que l'API soit prête.

**Livrable :** la page `/` complète et fonctionnelle sur ordinateur et téléphone.

---

### Aliou — Espace administrateur

**Objectif :** les pages où l'administrateur gère les pénalités.

**Tâches et méthode :**

1. **Client API et types partagés** (`lib/api.ts`, `lib/types.ts`)
   - Écrire les types TypeScript à partir du contrat d'API (`Route`, `Penalty`, `Edge`...).
   - Une fonction par endpoint ; pour les routes admin, ajouter automatiquement l'en-tête `Authorization: Bearer <jwt>`.
   - Livrer **en premier** (jour 3) : Elnis l'utilise aussi.
2. **Connexion** (`app/admin/login/page.tsx`)
   - Formulaire e-mail / mot de passe avec `supabase.auth.signInWithPassword`.
   - Protéger `/admin` : si aucune session, rediriger vers `/admin/login`. Si l'API répond `403`, afficher « Accès réservé aux administrateurs ».
3. **Sélection d'une route sur la carte**
   - Réutiliser `MapView` d'Elnis. Au clic, appeler `/admin/edges/nearest` et surligner le tronçon renvoyé.
   - Case à cocher « toute la rue » : passe `whole_way=true` et surligne toute la rue.
4. **Formulaire de pénalité** (`components/admin/PenaltyForm.tsx`)
   - Champs : niveau (liste déroulante), motif (texte), date de début et de fin.
   - Vérifications côté client : motif obligatoire, date de fin après la date de début.
   - Envoi via `POST /admin/penalties`, puis rafraîchissement de la liste et de la carte.
5. **Liste et gestion des pénalités** (`components/admin/PenaltyList.tsx`)
   - Tableau filtrable (actives, à venir, passées) : rue, niveau, motif, dates.
   - Boutons **Modifier** (`PATCH`) et **Retirer** (`DELETE`, avec confirmation dans l'interface, pas `window.confirm`).
   - Toutes les pénalités actives sont aussi affichées sur la carte, colorées par niveau.
6. **Déploiement du frontend** sur Vercel, avec les variables d'environnement.

**Dépend de :** contrat d'API (jour 2), compte admin de test fourni par Emmanuela (jour 5).

**Livrable :** les pages `/admin/login` et `/admin` complètes, et le frontend en ligne.

---

### Mounir — Données, graphe et accroche au réseau

**Objectif :** transformer OpenStreetMap en graphe exploitable et le charger dans le serveur.

**Tâches et méthode :**

1. **Prototype** (avec Lambert, jours 1 et 2)
   - `osmnx.graph_from_polygon` sur Littoral + Atlantique, `network_type="drive"`.
   - Dijkstra simple avec `networkx`, affichage avec `folium`. Sert de référence pour valider le moteur final.
2. **Script `build_graph.py`**
   - Récupérer les limites des deux départements avec `osmnx.geocode_to_gdf`, puis télécharger le réseau.
   - Garder le graphe **orienté** (sens uniques respectés), et une seule arête entre deux nœuds (la plus courte).
   - Estimer la vitesse de chaque arête selon le type de route (`highway`) avec `ox.add_edge_speeds`.
   - Renuméroter les nœuds de 0 à N−1, trier les arêtes par nœud de départ, construire `offsets`, `targets`, `lengths`, `speeds`, `way_ids`, `node_coords`, et les sauvegarder avec `numpy.save`.
   - Exporter `edges.geojson` (géométrie et nom de chaque arête, même ordre que les tableaux).
3. **Chargement du graphe** (`routing/graph.py`)
   - Charger les tableaux une seule fois au démarrage (événement `lifespan` de FastAPI), avec `numpy.load(..., mmap_mode="r")`.
   - Fournir une fonction `edge_geometry(edge_id)` pour reconstruire un tracé.
4. **Accroche au réseau** (`routing/snapping.py`)
   - `nearest_node(lat, lon)` : `cKDTree` sur les coordonnées des nœuds (projeter en mètres avant, pour des distances correctes).
   - `nearest_edge(lat, lon)` : `cKDTree` sur les milieux des arêtes, puis départager les 10 plus proches par distance réelle au segment. Utilisé par la page admin.
   - Refuser un point à plus de 500 m de toute route (hors zone).
5. **Conteneurisation et déploiement**
   - `Dockerfile` du backend (image Python 3.11 slim), qui copie `data/graph/`.
   - Déploiement sur un hébergeur qui accepte au moins 1 Go de RAM (Render, Railway ou une VM).

**Dépend de :** rien, c'est le premier maillon. Format des fichiers à figer avec Lambert le jour 2.

**Livrable :** `data/graph/` généré, `graph.py` et `snapping.py` testés, backend en ligne.

---

### Lambert — Algorithmes : Dijkstra et pénalités

**Objectif :** le moteur de calcul, cœur du projet.

**Tâches et méthode :**

1. **Prototype** (avec Mounir, jours 1 et 2) : écrire le Dijkstra de référence en Python pur, sur un petit graphe.
2. **Dijkstra compilé** (`routing/dijkstra.py`)
   - Fonction `@njit` qui prend `offsets`, `targets`, `costs`, `source`, `target`, et renvoie `dist`, `pred`, nombre de nœuds explorés.
   - Le module `heapq` n'est pas utilisable dans Numba : écrire un **tas binaire maison** sur des tableaux NumPy (`push`, `pop`), avec la suppression paresseuse des entrées obsolètes.
   - Arrêt anticipé dès que `target` est extrait du tas. Ignorer les arêtes de coût infini.
   - Reconstruire le chemin en remontant `pred`, sous forme de liste d'identifiants d'arêtes.
3. **Application des pénalités admin**
   - Au moment du calcul : `costs = lengths * admin_factors` (tableau fourni par `penalties.py`).
4. **Méthode des pénalités** (`routing/alternatives.py`)
   - Suivre l'algorithme décrit plus haut : copie des coûts, × 1,4 sur les arêtes des chemins déjà trouvés, relance de Dijkstra.
   - Calculer le recouvrement entre deux chemins (longueur commune / longueur du plus court) et écarter les alternatives au-dessus de 70 %.
   - Ne **jamais** modifier le tableau partagé : toujours travailler sur une copie (`costs.copy()`).
5. **Fonction d'intégration** pour Emmanuela :
   `compute_routes(source, target, admin_factors, k) -> list[Route]` avec distance réelle, durée (`lengths / speeds`) et arêtes pénalisées.
6. **Tests et performances** (`tests/test_dijkstra.py`)
   - Comparer les résultats au prototype `networkx` sur 100 paires de points tirées au hasard : distances identiques.
   - Cas limites : départ = arrivée, destination inaccessible, route fermée sur le seul chemin possible.
   - Mesurer le temps moyen de calcul et le nombre de nœuds explorés ; objectif : moins de 100 ms pour 3 chemins.

**Dépend de :** fichiers du graphe de Mounir (jour 4). En attendant, tester sur un petit graphe fabriqué à la main.

**Livrable :** `dijkstra.py` et `alternatives.py` testés, `compute_routes` prête à être appelée.

---

### Emmanuela — API, base de données et sécurité

**Objectif :** relier le frontend au moteur, stocker les données et protéger l'espace admin.

**Tâches et méthode :**

1. **Contrat d'API** (jour 2, avec Elnis et Aliou) : figer le format de toutes les requêtes et réponses décrites dans la section [API](#api), et créer des modèles Pydantic correspondants.
2. **Base de données** (`db/schema.sql`)
   - Créer les tables `places`, `penalties`, `profiles`, avec un index spatial `GIST` sur `places.geom` et un index `GIN` (`gin_trgm_ops`) sur `places.name`.
   - Script `import_places.py` : extraire les lieux nommés d'OSM avec `osmnx.features_from_polygon` (marchés, écoles, hôpitaux, lieux de culte, quartiers) et les insérer.
3. **Endpoints publics**
   - `/route` : accrocher les points (`snapping.py`), appeler `compute_routes`, mettre en forme la réponse.
   - `/places` : requête `similarity(name, :q)` avec pg_trgm, triée par score, 10 résultats maximum.
   - `/penalties/active` : pénalités actives avec leur géométrie.
4. **Sécurité** (`auth.py`)
   - Dépendance FastAPI `require_admin` : vérifier le JWT Supabase avec `python-jose` et `SUPABASE_JWT_SECRET`, puis le rôle `admin` dans `profiles`. Sinon : `401` (non connecté) ou `403` (pas admin).
   - Configurer CORS pour n'accepter que l'URL du frontend.
   - Créer le compte admin de test et le transmettre à Aliou (jour 5).
5. **Endpoints admin et synchronisation des pénalités** (`routes/admin.py`, `routing/penalties.py`)
   - CRUD des pénalités, avec validation : niveau connu, motif non vide, dates cohérentes, arêtes existantes.
   - `penalties.py` garde un tableau `admin_factors` (un facteur par arête, 1,0 par défaut). Au démarrage, le reconstruire depuis la base. Après chaque `POST`, `PATCH` ou `DELETE`, le reconstruire aussi.
   - Une tâche de fond toutes les minutes reconstruit le tableau, pour activer ou désactiver les pénalités selon leurs dates.
6. **Tests de l'API** (`tests/test_api.py`) avec `TestClient` de FastAPI : réponses valides, erreurs `422`, accès admin refusé sans jeton.

**Dépend de :** `snapping.py` (Mounir) et `compute_routes` (Lambert). En attendant, renvoyer des réponses simulées conformes au contrat.

**Livrable :** API complète et documentée sur `/docs`, base de données en place, espace admin sécurisé.

---

### Points de synchronisation

| Jour | Rendez-vous | Participants |
|---|---|---|
| J2 | Contrat d'API figé et publié dans `docs/api.md` | Toute l'équipe |
| J2 | Format des fichiers du graphe figé | Mounir, Lambert |
| J3 | Livraison de `MapView` et du client API | Elnis, Aliou |
| J4 | Graphe complet disponible | Mounir → Lambert, Emmanuela |
| J7 | Première intégration de bout en bout (un itinéraire affiché depuis l'API réelle) | Toute l'équipe |
| J11 | Gel des fonctionnalités : uniquement des corrections après | Toute l'équipe |

---

## Planning sur deux semaines

| Jours | Elnis | Aliou | Mounir | Lambert | Emmanuela |
|---|---|---|---|---|---|
| J1–J2 | Maquette de la page, contrat d'API | Contrat d'API, types | Prototype osmnx | Prototype Dijkstra | Contrat d'API, schéma de base |
| J3–J4 | `MapView`, marqueurs | Client API, connexion | `build_graph.py` | Tas binaire et Dijkstra Numba | Tables, import des lieux |
| J5–J7 | Recherche, affichage des tracés | Sélection de route sur la carte | `graph.py`, `snapping.py` | Pénalités admin, tests | `/route`, `/places`, `auth.py` |
| J8–J10 | Panneau des résultats, tronçons pénalisés | Formulaire et liste des pénalités | Docker, déploiement backend | Méthode des pénalités (alternatives) | Endpoints admin, synchronisation RAM |
| J11–J12 | États d'erreur, mobile | Déploiement Vercel | Aide à l'intégration | Mesures de performance | Tests de l'API |
| J13–J14 | Tests et corrections, préparation de la démonstration | | | | |

---

## Règles de travail

- Une branche par fonctionnalité (`feature/map-view`, `feature/dijkstra-numba`, `feature/admin-penalties`...), jamais de commit direct sur `main`.
- Toute pull request est relue par au moins un autre membre avant fusion.
- Une fonctionnalité n'est terminée que si elle est testée et documentée.
- Une issue GitHub par tâche, assignée à son responsable, suivie dans un tableau **Projects** (À faire / En cours / Terminé).
- Point d'avancement rapide chaque jour : ce qui est fait, ce qui bloque.

---

## Licence et attributions

Code source : licence MIT (voir `LICENSE`).

Données cartographiques : © les contributeurs d'[OpenStreetMap](https://www.openstreetmap.org/copyright), disponibles sous licence ODbL. Cette attribution doit rester visible sur la carte de l'application.

---

## Équipe

Elnis · Aliou · Mounir · Lambert · Emmanuela · Powell Fagnon
