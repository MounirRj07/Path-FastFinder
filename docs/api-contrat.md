# Contrat d'API (version 1)

Ce document décrit ce que l'interface doit envoyer à l'API et ce qu'elle reçoit en retour.
Il est écrit pour Elnis et Aliou. Si un point doit changer, on en discute avant de modifier le code.

- Adresse en local : `http://127.0.0.1:8000`
- Page de test interactive : `http://127.0.0.1:8000/docs`
- Format des échanges : JSON
- Lancer l'API : depuis le dossier `api`, `python -m uvicorn main:app --reload`
- Autorisation CORS : l'API accepte `http://localhost:3000`. L'adresse de l'interface en ligne sera ajoutée au déploiement.

## Ce qui est réel et ce qui est encore simulé

| Route | État |
|---|---|
| `GET /centers` | Réel (base de données Supabase, 2 centres de test pour l'instant) |
| `GET /places` | Réel, mais renvoie des résultats seulement quand la table des lieux est remplie |
| `GET /history`, `POST /history` | Réel, connexion requise |
| `GET /favorites`, `POST /favorites`, `DELETE /favorites/{id}` | Réel, connexion requise |
| `POST /route` | **Simulé** : réponse de forme correcte, valeurs inventées, en attendant Dijkstra |
| `GET /scenarios` | **Simulé** : liste fixe |
| `GET /roads/nearest` | **Simulé** : réponse fixe |

La forme des réponses simulées est définitive. Seules les valeurs vont changer.

## Connexion et jeton

La connexion se fait directement auprès de Supabase Auth, pas auprès de notre API.
L'interface obtient un jeton, puis l'envoie dans l'en-tête de chaque demande aux routes protégées :

    Authorization: Bearer <jeton>

- Le jeton expire au bout d'environ une heure. La bibliothèque Supabase le renouvelle automatiquement.
- Sans jeton ou avec un jeton invalide, les routes protégées répondent `401`.
- Le jeton est un secret : ne jamais l'écrire dans le code, dans un fichier envoyé sur GitHub ou dans un message d'équipe.

Exemple avec `@supabase/supabase-js` (variables d'environnement de l'interface) :

```ts
import { createClient } from "@supabase/supabase-js";

const supabase = createClient(
  process.env.NEXT_PUBLIC_SUPABASE_URL!,
  process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY!
);

// Connexion
const { data, error } = await supabase.auth.signInWithPassword({ email, password });

// Récupérer le jeton courant
const { data: sessionData } = await supabase.auth.getSession();
const token = sessionData.session?.access_token;

// Appeler une route protégée
const res = await fetch(`${API_URL}/favorites`, {
  headers: { Authorization: `Bearer ${token}` },
});
```

## États de route (valeurs exactes)

Proposition à valider avec toute l'équipe. Ces mots doivent être identiques partout (interface, API, calcul).

| Valeur | Sens |
|---|---|
| `fluide` | Circulation normale (coefficient ×1) |
| `dense` | Trafic dense (×1,5) |
| `tres_dense` | Trafic très dense (×3) |
| `inondee` | Inondée mais passable (×4, valeur à calibrer) |
| `bloquee` | Route retirée du graphe |

Un état inconnu dans `road_overrides` provoque une erreur `422`.

## Types TypeScript

```ts
export type RoadState = "fluide" | "dense" | "tres_dense" | "inondee" | "bloquee";

export interface Point { lat: number; lon: number }

export interface RouteRequest {
  start: Point;
  end: Point;
  scenario?: string | null;
  road_overrides?: Record<string, RoadState>;
}

export interface RouteResult {
  coordinates: [number, number][]; // [longitude, latitude]
  distance_m: number;              // mètres
  duration_s: number;              // secondes
}

export interface RouteResponse {
  shortest: RouteResult;
  fastest: RouteResult;
  identical: boolean;
}

export interface Center { id: number; name: string; lat: number; lon: number }
export interface Place { id: number; name: string; lat: number; lon: number }
export interface Scenario { id: string; name: string }
export interface NearestRoad { road_id: string; name: string; state: RoadState }

export interface HistoryItem {
  id: number;
  center_id: number | null;
  end_lat: number;
  end_lon: number;
  shortest_m: number | null;
  fastest_s: number | null;
  scenario: string | null;
  created_at: string;
}

export interface FavoriteItem {
  id: number;
  center_id: number | null;
  end_lat: number;
  end_lon: number;
  label: string | null;
}
```

## Routes publiques

### POST /route

Calcule l'itinéraire le plus court et le plus rapide.

Corps de la requête :

```json
{
  "start": { "lat": 6.40, "lon": 2.33 },
  "end":   { "lat": 6.45, "lon": 2.35 },
  "scenario": "pluie",
  "road_overrides": { "r_0042": "inondee" }
}
```

- `start` (centre de secours) et `end` (lieu d'intervention) sont obligatoires.
- `scenario` et `road_overrides` sont facultatifs.
- Chaque demande transporte son scénario et ses modifications : le serveur ne garde aucun état.

Réponse `200` :

```json
{
  "shortest": { "coordinates": [[2.33, 6.40], [2.35, 6.45]], "distance_m": 3200, "duration_s": 480 },
  "fastest":  { "coordinates": [[2.33, 6.40], [2.35, 6.45]], "distance_m": 3500, "duration_s": 420 },
  "identical": false
}
```

- `coordinates` : longitude d'abord, puis latitude (ordre attendu par MapLibre).
- `identical` vaut `true` si les deux itinéraires sont les mêmes : afficher alors un message.

Erreurs :

- `404` : aucun chemin entre le départ et l'arrivée (afficher un message clair à l'opérateur).
- `422` : données invalides ou état de route inconnu.

### GET /centers

Liste des centres de secours.

```json
[ { "id": 1, "name": "Centre de test A", "lat": 6.3854, "lon": 2.3432 } ]
```

### GET /places?q=texte&limit=8

Recherche de lieux, tolérante aux fautes de frappe. `q` fait au moins 2 caractères.
Renvoie au plus `limit` résultats, les plus ressemblants d'abord.

```json
[ { "id": 12, "name": "Marché de Godomey", "lat": 6.39, "lon": 2.34 } ]
```

### GET /scenarios

Liste des scénarios prédéfinis (simulé pour l'instant).

```json
[ { "id": "normal", "name": "Situation normale" },
  { "id": "pointe", "name": "Heure de pointe" },
  { "id": "pluie", "name": "Forte pluie" },
  { "id": "accident", "name": "Accident sur un axe" } ]
```

### GET /roads/nearest?lat=6.4&lon=2.3

Route la plus proche d'un clic sur la carte (simulé pour l'instant).

```json
{ "road_id": "r_0001", "name": "Route de test", "state": "fluide" }
```

## Routes protégées (en-tête `Authorization: Bearer <jeton>` obligatoire)

Chaque utilisateur ne voit que ses propres données.

### GET /history

Les 50 derniers itinéraires de l'utilisateur, du plus récent au plus ancien. Renvoie une liste de `HistoryItem`.

### POST /history

Enregistre un itinéraire calculé.

```json
{
  "center_id": 1,
  "end_lat": 6.45,
  "end_lon": 2.35,
  "shortest_m": 3200,
  "fastest_s": 480,
  "scenario": "normal"
}
```

Réponse : `{ "id": 7 }`. Seuls `end_lat` et `end_lon` sont obligatoires.

### GET /favorites

Liste des trajets favoris de l'utilisateur. Renvoie une liste de `FavoriteItem`.

### POST /favorites

```json
{ "center_id": 1, "end_lat": 6.45, "end_lon": 2.35, "label": "Hôpital de zone" }
```

Réponse : `{ "id": 3 }`. Seuls `end_lat` et `end_lon` sont obligatoires.

### DELETE /favorites/{id}

Supprime un favori de l'utilisateur. Réponse : `{ "deleted": 3 }`. Erreur `404` si le favori n'existe pas ou n'appartient pas à l'utilisateur.

## Codes d'erreur

| Code | Sens |
|---|---|
| `401` | Jeton absent, invalide ou expiré |
| `404` | Aucun chemin (route), favori introuvable |
| `422` | Données mal formées ou état de route inconnu |
| `500` | Erreur du serveur |

## Exemple d'appel pour calculer un itinéraire

```ts
const API_URL = "http://127.0.0.1:8000";

const res = await fetch(`${API_URL}/route`, {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({
    start: { lat: 6.40, lon: 2.33 },
    end: { lat: 6.45, lon: 2.35 },
    scenario: "pluie",
  }),
});

if (res.status === 404) {
  // aucun chemin : afficher un message clair
} else if (res.ok) {
  const result: RouteResponse = await res.json();
}
```

## Points à valider en équipe

1. La liste des états de route (section ci-dessus).
2. Les identifiants de scénarios (`normal`, `pointe`, `pluie`, `accident`).
3. Le format des identifiants de route (`r_0001`), à fixer avec la construction du graphe.
4. L'adresse de l'interface en ligne, à ajouter à l'autorisation CORS de l'API au déploiement.
