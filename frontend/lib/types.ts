// Types partagés, alignés sur le contrat d'API (README, section API).
// À valider avec Emmanuela au J2 : les champs marqués (*) ne sont pas
// encore définis dans le README.

/** Coordonnée GeoJSON : [longitude, latitude] */
export type LngLat = [number, number];

// (*) Valeurs exactes du niveau "route fermée" à confirmer ("fermee" ?)
export type PenaltyLevel = "leger" | "moyen" | "fort" | "fermee";

export const PENALTY_LEVELS: {
  value: PenaltyLevel;
  label: string;
  factor: string;
  color: string;
}[] = [
  { value: "leger", label: "Léger", factor: "× 1,5", color: "#eab308" },
  { value: "moyen", label: "Moyen", factor: "× 3", color: "#f97316" },
  { value: "fort", label: "Fort", factor: "× 10", color: "#ea580c" },
  { value: "fermee", label: "Route fermée", factor: "∞", color: "#dc2626" },
];

// ---------- Routes publiques ----------

export interface PenalizedSegment {
  level: PenaltyLevel;
  reason: string;
  geometry: LngLat[];
}

export interface Route {
  rank: number;
  distance_m: number;
  duration_s: number;
  geometry: LngLat[];
  penalized_segments: PenalizedSegment[];
}

export interface RouteResponse {
  routes: Route[];
  stats: { compute_time_ms: number; nodes_explored: number };
}

export interface RouteParams {
  from_lat: number;
  from_lon: number;
  to_lat: number;
  to_lon: number;
  alternatives?: 0 | 1 | 2;
}

export interface Place {
  id: number;
  name: string;
  category: string;
  lat: number;
  lon: number;
}

// ---------- Routes administrateur ----------

/** (*) Réponse de GET /admin/edges/nearest */
export interface NearestEdge {
  edge_ids: number[]; // tous les tronçons de la rue si whole_way=true
  way_id: number;
  name: string | null; // rue sans nom possible
  geometry: LngLat[];
}

/** (*) Réponse de GET /admin/penalties et /penalties/active */
export interface Penalty {
  id: number;
  edge_ids: number[];
  way_id: number | null;
  street_name: string | null;
  level: PenaltyLevel;
  factor: number | null; // null si fermée (infini)
  reason: string;
  starts_at: string; // ISO 8601 UTC
  ends_at: string;
  created_at: string;
  geometry: LngLat[][]; // une ligne par tronçon
}

/** Corps de POST /admin/penalties */
export interface PenaltyInput {
  edge_ids: number[];
  level: PenaltyLevel;
  reason: string;
  starts_at: string;
  ends_at: string;
}

/** (*) Corps de PATCH /admin/penalties/{id} : champs modifiables à confirmer */
export type PenaltyUpdate = Partial<Omit<PenaltyInput, "edge_ids">>;

/** État d'une pénalité, calculé côté client à partir des dates */
export type PenaltyStatus = "active" | "upcoming" | "past";

export function getPenaltyStatus(p: Penalty, now = new Date()): PenaltyStatus {
  if (now < new Date(p.starts_at)) return "upcoming";
  if (now > new Date(p.ends_at)) return "past";
  return "active";
}
