// MODE DÉMO : activé avec NEXT_PUBLIC_MOCK=true dans frontend/.env.local
// Ni Supabase ni l'API ne sont contactés. Les données sont gardées dans le
// localStorage du navigateur (elles survivent à un rechargement de page).
//
// Identifiants de démonstration : admin@demo.local / demo1234

import type {
  LngLat,
  NearestEdge,
  Penalty,
  PenaltyInput,
  PenaltyLevel,
  PenaltyUpdate,
} from "./types";

export const MOCK = process.env.NEXT_PUBLIC_MOCK === "true";

export const DEMO_EMAIL = "admin@demo.local";
export const DEMO_PASSWORD = "demo1234";

const SESSION_KEY = "mock_session";
const PENALTIES_KEY = "mock_penalties";

const FACTORS: Record<PenaltyLevel, number | null> = {
  leger: 1.5,
  moyen: 3,
  fort: 10,
  fermee: null, // infini
};

const delay = (ms = 150) => new Promise((r) => setTimeout(r, ms));

// ---------- Stockage navigateur (toujours dans un try/catch) ----------

function read<T>(key: string): T | null {
  try {
    const raw = window.localStorage.getItem(key);
    return raw ? (JSON.parse(raw) as T) : null;
  } catch {
    return null;
  }
}

function write(key: string, value: unknown) {
  try {
    window.localStorage.setItem(key, JSON.stringify(value));
  } catch {
    /* stockage indisponible : on continue sans sauvegarder */
  }
}

function remove(key: string) {
  try {
    window.localStorage.removeItem(key);
  } catch {
    /* ignoré */
  }
}

// ---------- Fausses pénalités ----------

const line = (lon: number, lat: number): LngLat[] => [
  [lon, lat],
  [lon + 0.004, lat + 0.002],
];

function seed(): Penalty[] {
  const now = Date.now();
  const h = 3600 * 1000;
  const d = 24 * h;
  const iso = (ms: number) => new Date(ms).toISOString();

  return [
    {
      id: 1,
      edge_ids: [10432, 10433],
      way_id: 5001,
      street_name: "Route des Pêches",
      level: "fort",
      factor: 10,
      reason: "Travaux de voirie",
      starts_at: iso(now - d),
      ends_at: iso(now + 5 * d),
      created_at: iso(now - 2 * d),
      geometry: [line(2.35, 6.45), line(2.354, 6.452)],
    },
    {
      id: 2,
      edge_ids: [20871],
      way_id: 5002,
      street_name: "Avenue de l'Université",
      level: "moyen",
      factor: 3,
      reason: "Embouteillage fréquent",
      starts_at: iso(now - 3 * h),
      ends_at: iso(now + 2 * d),
      created_at: iso(now - 3 * h),
      geometry: [line(2.33, 6.43)],
    },
    {
      id: 3,
      edge_ids: [30115],
      way_id: 5003,
      street_name: "Rue du Marché",
      level: "fermee",
      factor: null,
      reason: "Chaussée inondée",
      starts_at: iso(now + 2 * d),
      ends_at: iso(now + 4 * d),
      created_at: iso(now - d),
      geometry: [line(2.37, 6.47)],
    },
    {
      id: 4,
      edge_ids: [40222],
      way_id: 5004,
      street_name: null,
      level: "leger",
      factor: 1.5,
      reason: "Route dégradée",
      starts_at: iso(now - 10 * d),
      ends_at: iso(now - 8 * d),
      created_at: iso(now - 11 * d),
      geometry: [line(2.31, 6.41)],
    },
  ];
}

function load(): Penalty[] {
  const saved = read<Penalty[]>(PENALTIES_KEY);
  if (saved) return saved;
  const initial = seed();
  write(PENALTIES_KEY, initial);
  return initial;
}

function edgeGeometry(ids: number[]): LngLat[][] {
  return ids.map((id) =>
    line(2.3 + (id % 100) * 0.001, 6.4 + (Math.floor(id / 100) % 100) * 0.001)
  );
}

// ---------- Fonctions appelées par api.ts ----------

export async function mockList(): Promise<Penalty[]> {
  await delay();
  return load();
}

export async function mockActive(): Promise<Penalty[]> {
  await delay();
  const now = Date.now();
  return load().filter(
    (p) => new Date(p.starts_at).getTime() <= now && now <= new Date(p.ends_at).getTime()
  );
}

export async function mockCreate(input: PenaltyInput): Promise<Penalty> {
  await delay();
  const all = load();
  const penalty: Penalty = {
    id: Math.max(0, ...all.map((p) => p.id)) + 1,
    edge_ids: input.edge_ids,
    way_id: null,
    street_name: `Tronçon ${input.edge_ids[0]}`,
    level: input.level,
    factor: FACTORS[input.level],
    reason: input.reason,
    starts_at: input.starts_at,
    ends_at: input.ends_at,
    created_at: new Date().toISOString(),
    geometry: edgeGeometry(input.edge_ids),
  };
  write(PENALTIES_KEY, [...all, penalty]);
  return penalty;
}

/** Renvoie null si l'identifiant n'existe pas */
export async function mockUpdate(
  id: number,
  changes: PenaltyUpdate
): Promise<Penalty | null> {
  await delay();
  const all = load();
  const index = all.findIndex((p) => p.id === id);
  if (index === -1) return null;

  const updated: Penalty = { ...all[index], ...changes };
  if (changes.level) updated.factor = FACTORS[changes.level];
  all[index] = updated;
  write(PENALTIES_KEY, all);
  return updated;
}

/** Renvoie false si l'identifiant n'existe pas */
export async function mockDelete(id: number): Promise<boolean> {
  await delay();
  const all = load();
  const rest = all.filter((p) => p.id !== id);
  if (rest.length === all.length) return false;
  write(PENALTIES_KEY, rest);
  return true;
}

export async function mockNearestEdge(
  lat: number,
  lon: number,
  wholeWay: boolean
): Promise<NearestEdge> {
  await delay();
  const base = Math.abs(Math.round(lat * 1e4) * 31 + Math.round(lon * 1e4)) % 90000;
  const ids = wholeWay ? [base, base + 1, base + 2] : [base];
  return {
    edge_ids: ids,
    way_id: base,
    name: "Route de démonstration",
    geometry: ids.map((_, i) => [lon + i * 0.002, lat + i * 0.001] as LngLat),
  };
}

// ---------- Fausse authentification (imite supabase.auth) ----------

interface MockSession {
  access_token: string;
  user: { email: string };
}

type Listener = (event: string, session: MockSession | null) => void;
const listeners = new Set<Listener>();

function notify(event: string, session: MockSession | null) {
  listeners.forEach((l) => l(event, session));
}

export const mockSupabase = {
  auth: {
    async getSession() {
      return { data: { session: read<MockSession>(SESSION_KEY) }, error: null };
    },

    async signInWithPassword({
      email,
      password,
    }: {
      email: string;
      password: string;
    }) {
      await delay(300);
      if (email === DEMO_EMAIL && password === DEMO_PASSWORD) {
        const session: MockSession = { access_token: "mock-token", user: { email } };
        write(SESSION_KEY, session);
        notify("SIGNED_IN", session);
        return { data: { session }, error: null };
      }
      return {
        data: { session: null },
        error: { message: "Invalid login credentials" },
      };
    },

    async signOut() {
      remove(SESSION_KEY);
      notify("SIGNED_OUT", null);
      return { error: null };
    },

    onAuthStateChange(cb: Listener) {
      listeners.add(cb);
      return {
        data: { subscription: { unsubscribe: () => void listeners.delete(cb) } },
      };
    },
  },
};
