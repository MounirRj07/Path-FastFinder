import { supabase } from "./supabase";
import {
  MOCK,
  mockActive,
  mockCreate,
  mockDelete,
  mockList,
  mockNearestEdge,
  mockUpdate,
} from "./mock";
import type {
  NearestEdge,
  Penalty,
  PenaltyInput,
  PenaltyUpdate,
  Place,
  RouteParams,
  RouteResponse,
} from "./types";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

// ---------- Erreurs ----------

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
    /** Erreurs 422 : { nom_du_champ: message } */
    public fieldErrors: Record<string, string> = {}
  ) {
    super(message);
    this.name = "ApiError";
  }

  /** Non connecté ou session expirée : rediriger vers /admin/login */
  get isUnauthorized() {
    return this.status === 401;
  }
  /** Connecté mais pas administrateur : « Accès réservé aux administrateurs » */
  get isForbidden() {
    return this.status === 403;
  }
}

/** Transforme la réponse d'erreur FastAPI en ApiError. */
async function toApiError(res: Response): Promise<ApiError> {
  let body: any = null;
  try {
    body = await res.json();
  } catch {
    /* corps vide ou non JSON */
  }

  // 422 FastAPI : { detail: [{ loc: ["body", "reason"], msg: "..." }] }
  if (res.status === 422 && Array.isArray(body?.detail)) {
    const fieldErrors: Record<string, string> = {};
    for (const d of body.detail) {
      const field = String(d.loc?.[d.loc.length - 1] ?? "form");
      fieldErrors[field] = d.msg;
    }
    return new ApiError(422, "Données invalides", fieldErrors);
  }

  const message =
    typeof body?.detail === "string"
      ? body.detail
      : `Erreur ${res.status} ${res.statusText}`;
  return new ApiError(res.status, message);
}

// ---------- Requête générique ----------

interface RequestOptions {
  method?: "GET" | "POST" | "PATCH" | "DELETE";
  body?: unknown;
  query?: Record<string, string | number | boolean | undefined>;
  admin?: boolean; // ajoute l'en-tête Authorization
}

async function request<T>(path: string, opts: RequestOptions = {}): Promise<T> {
  const { method = "GET", body, query, admin = false } = opts;

  const url = new URL(path, API_URL);
  if (query) {
    for (const [k, v] of Object.entries(query)) {
      if (v !== undefined) url.searchParams.set(k, String(v));
    }
  }

  const headers: Record<string, string> = {};
  if (body !== undefined) headers["Content-Type"] = "application/json";

  if (admin) {
    // On relit la session à chaque appel : Supabase renouvelle le jeton seul.
    const { data } = await supabase.auth.getSession();
    const token = data.session?.access_token;
    if (!token) throw new ApiError(401, "Non connecté");
    headers["Authorization"] = `Bearer ${token}`;
  }

  let res: Response;
  try {
    res = await fetch(url, {
      method,
      headers,
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
  } catch {
    throw new ApiError(0, "Serveur injoignable. Vérifiez votre connexion.");
  }

  if (!res.ok) throw await toApiError(res);
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

// ---------- Endpoints publics (utilisés surtout par Elnis) ----------

export const getRoute = (p: RouteParams) =>
  request<RouteResponse>("/route", { query: { ...p } });

export const searchPlaces = (q: string) =>
  request<Place[]>("/places", { query: { q } });

export const getActivePenalties = () =>
  MOCK ? mockActive() : request<Penalty[]>("/penalties/active");

// ---------- Endpoints administrateur ----------

export const getNearestEdge = (lat: number, lon: number, wholeWay = false) =>
  MOCK
    ? mockNearestEdge(lat, lon, wholeWay)
    : request<NearestEdge>("/admin/edges/nearest", {
        admin: true,
        query: { lat, lon, whole_way: wholeWay },
      });

export const listPenalties = () =>
  MOCK ? mockList() : request<Penalty[]>("/admin/penalties", { admin: true });

export const createPenalty = (input: PenaltyInput) =>
  MOCK
    ? mockCreate(input)
    : request<Penalty>("/admin/penalties", {
        admin: true,
        method: "POST",
        body: input,
      });

export const updatePenalty = async (id: number, changes: PenaltyUpdate) => {
  if (!MOCK) {
    return request<Penalty>(`/admin/penalties/${id}`, {
      admin: true,
      method: "PATCH",
      body: changes,
    });
  }
  const updated = await mockUpdate(id, changes);
  if (!updated) throw new ApiError(404, "Pénalité introuvable");
  return updated;
};

export const deletePenalty = async (id: number) => {
  if (!MOCK) {
    return request<void>(`/admin/penalties/${id}`, {
      admin: true,
      method: "DELETE",
    });
  }
  if (!(await mockDelete(id))) throw new ApiError(404, "Pénalité introuvable");
};
