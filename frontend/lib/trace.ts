// lib/trace.ts
// Logique de la visualisation pas à pas de Dijkstra (sans React ni carte) :
// types de la réponse /route/trace, état du graphe à l'étape k, texte
// explicatif, et conversion en GeoJSON pour MapLibre.

export type Point = [number, number]; // [lng, lat]

// Types GeoJSON minimaux (compatibles avec source.setData de MapLibre)
export type Feat = {
  type: "Feature";
  properties: Record<string, string | number | boolean>;
  geometry: { type: "LineString"; coordinates: Point[] } | { type: "Point"; coordinates: Point };
};
export type FC = { type: "FeatureCollection"; features: Feat[] };

export type TraceRelax = {
  edge: number;
  to: number;
  status: "improved" | "kept" | "closed";
  old_dist: number | null;
  new_dist: number | null;
};

export type TraceStep = { node: number; dist: number | null; relax: TraceRelax[] };

export type TraceEdge = {
  id: number;
  from: number;
  to: number;
  length_m: number;
  factor: number | null; // null = route fermée
  cost: number | null; // null = route fermée
  name: string;
  geometry: Point[];
};

export type TraceNode = { id: number; lon: number; lat: number };

export type TraceData = {
  source: number;
  target: number;
  nodes: TraceNode[];
  edges: TraceEdge[];
  steps: TraceStep[];
  path: { edges: number[]; nodes: number[]; distance_m: number; cost: number | null } | null;
  stats: {
    nodes_explored: number;
    edges_examined: number;
    found: boolean;
    truncated: boolean;
    compute_time_ms: number;
  };
};

export const COLORS = {
  unseen: "#cbd5e1",
  rejected: "#94a3b8",
  treeSettled: "#1d4ed8",
  treeFrontier: "#f59e0b",
  closed: "#dc2626",
  path: "#16a34a",
  current: "#7c3aed",
  source: "#16a34a",
  target: "#dc2626",
} as const;

export const fmt = (x: number) => String(Math.round(x));

// ---------------------------------------------------------------------------
// Préparation (une seule fois par trace)
// ---------------------------------------------------------------------------

type Pair = { key: string; edges: TraceEdge[]; geometry: Point[]; mid: Point; label: string; penalized: boolean };

export type Prepared = {
  edgeById: Map<number, TraceEdge>;
  nodeById: Map<number, TraceNode>;
  pairs: Pair[];
};

function midpoint(geom: Point[]): Point {
  if (geom.length === 1) return geom[0];
  const seg: number[] = [];
  let total = 0;
  for (let i = 1; i < geom.length; i++) {
    const d = Math.hypot(geom[i][0] - geom[i - 1][0], geom[i][1] - geom[i - 1][1]);
    seg.push(d);
    total += d;
  }
  let half = total / 2;
  for (let i = 0; i < seg.length; i++) {
    if (half <= seg[i] || i === seg.length - 1) {
      const t = seg[i] > 0 ? half / seg[i] : 0;
      return [
        geom[i][0] + (geom[i + 1][0] - geom[i][0]) * t,
        geom[i][1] + (geom[i + 1][1] - geom[i][1]) * t,
      ];
    }
    half -= seg[i];
  }
  return geom[0];
}

/** Texte du coût d'un tronçon : « 120 », « 120×3=360 » (pénalité) ou « fermée ». */
export function edgeLabel(e: TraceEdge): string {
  if (e.cost === null) return "fermée";
  if (e.factor !== null && e.factor !== 1) return `${fmt(e.length_m)}×${e.factor}=${fmt(e.cost)}`;
  return fmt(e.cost);
}

export function prepareTrace(data: TraceData): Prepared {
  const edgeById = new Map(data.edges.map((e) => [e.id, e]));
  const nodeById = new Map(data.nodes.map((n) => [n.id, n]));

  // Une route à double sens = 2 arêtes superposées : on les dessine comme un seul tronçon.
  const groups = new Map<string, TraceEdge[]>();
  for (const e of data.edges) {
    const key = e.from < e.to ? `${e.from}-${e.to}` : `${e.to}-${e.from}`;
    const list = groups.get(key);
    if (list) list.push(e);
    else groups.set(key, [e]);
  }
  const pairs: Pair[] = [];
  groups.forEach((edges, key) => {
    const geometry = edges[0].geometry;
    const labels = Array.from(new Set(edges.map(edgeLabel)));
    pairs.push({
      key,
      edges,
      geometry,
      mid: midpoint(geometry),
      label: labels.join(" | "),
      penalized: edges.some((e) => e.cost === null || (e.factor !== null && e.factor !== 1)),
    });
  });
  return { edgeById, nodeById, pairs };
}

// ---------------------------------------------------------------------------
// État du graphe après k étapes
// ---------------------------------------------------------------------------

export type ViewState = {
  dist: Map<number, number>; // meilleure distance connue
  settled: Set<number>; // sommets fixés
  pred: Map<number, number>; // arête qui mène à chaque sommet (arbre des plus courts chemins)
  examined: Set<number>;
  closedEdges: Set<number>;
  current: number | null; // sommet fixé à l'étape k
  currentEdges: Set<number>; // arêtes examinées à l'étape k
};

export function stateAt(data: TraceData, k: number): ViewState {
  const dist = new Map<number, number>([[data.source, 0]]);
  const settled = new Set<number>();
  const pred = new Map<number, number>();
  const examined = new Set<number>();
  const closedEdges = new Set<number>();

  const n = Math.min(k, data.steps.length);
  for (let i = 0; i < n; i++) {
    const step = data.steps[i];
    settled.add(step.node);
    if (step.dist !== null) dist.set(step.node, step.dist);
    for (const r of step.relax) {
      examined.add(r.edge);
      if (r.status === "improved" && r.new_dist !== null) {
        dist.set(r.to, r.new_dist);
        pred.set(r.to, r.edge);
      } else if (r.status === "closed") {
        closedEdges.add(r.edge);
      }
    }
  }
  const last = n > 0 ? data.steps[n - 1] : null;
  return {
    dist,
    settled,
    pred,
    examined,
    closedEdges,
    current: last ? last.node : null,
    currentEdges: new Set(last ? last.relax.map((r) => r.edge) : []),
  };
}

// ---------------------------------------------------------------------------
// Texte explicatif de l'étape k
// ---------------------------------------------------------------------------

export type Narration = { title: string; lines: string[] };

const MAX_LINES = 6;

export function narrate(data: TraceData, prep: Prepared, k: number): Narration {
  const n = data.steps.length;

  if (k <= 0) {
    return {
      title: "Départ",
      lines: [
        `Le sommet ${data.source} (départ) reçoit la distance 0 ; tous les autres sont à l'infini (∞).`,
        "À chaque étape, Dijkstra fixe le sommet non fixé le plus proche du départ, puis examine ses voisins.",
      ],
    };
  }

  const step = data.steps[Math.min(k, n) - 1];
  const lines: string[] = [];

  if (k >= n && data.path) {
    lines.push(
      `Chemin trouvé : ${fmt(data.path.distance_m)} m` +
        (data.path.cost !== null ? ` (coût ${fmt(data.path.cost)}).` : ".") +
        " Il est reconstruit en remontant les arêtes retenues depuis l'arrivée (en vert)."
    );
  } else if (k >= n && !data.stats.found) {
    lines.push(
      data.stats.truncated
        ? "Trajet trop long : la trace a été arrêtée avant d'atteindre l'arrivée."
        : "Aucun chemin n'existe entre ces deux points."
    );
  }

  lines.push(
    `Sommet ${step.node} fixé à ${step.dist === null ? "?" : fmt(step.dist)} : c'est le plus proche du départ parmi ceux pas encore fixés, sa distance ne diminuera plus.`
  );

  if (step.node === data.target) {
    lines.push("C'est l'arrivée : Dijkstra s'arrête, plus aucun chemin plus court n'est possible.");
  } else if (step.relax.length === 0) {
    lines.push("Aucun voisin à examiner.");
  } else {
    const shown = step.relax.slice(0, MAX_LINES);
    for (const r of shown) {
      const edge = prep.edgeById.get(r.edge);
      const base = step.dist === null ? 0 : step.dist;
      if (r.status === "closed") {
        lines.push(`→ sommet ${r.to} : route fermée, ignorée.`);
      } else if (r.status === "improved") {
        const old = r.old_dist === null ? "∞" : fmt(r.old_dist);
        lines.push(
          `→ sommet ${r.to} : ${old} devient ${fmt(r.new_dist ?? 0)} (${fmt(base)} + ${edge && edge.cost !== null ? fmt(edge.cost) : "?"}). Mis à jour.`
        );
      } else {
        lines.push(
          `→ sommet ${r.to} : ${fmt(r.new_dist ?? 0)} n'améliore pas ${r.old_dist === null ? "∞" : fmt(r.old_dist)}. Inchangé.`
        );
      }
    }
    if (step.relax.length > MAX_LINES) lines.push(`… et ${step.relax.length - MAX_LINES} autre(s) voisin(s).`);
  }

  return { title: `Étape ${Math.min(k, n)} / ${n}`, lines };
}

// ---------------------------------------------------------------------------
// GeoJSON pour MapLibre
// ---------------------------------------------------------------------------

type Status = "unseen" | "rejected" | "tree_frontier" | "tree_settled" | "closed";
const PRIORITY: Record<Status, number> = {
  unseen: 1,
  rejected: 2,
  closed: 3,
  tree_frontier: 4,
  tree_settled: 5,
};

function edgeStatus(e: TraceEdge, s: ViewState): Status {
  if (s.pred.get(e.to) === e.id) return s.settled.has(e.to) ? "tree_settled" : "tree_frontier";
  if (s.closedEdges.has(e.id)) return "closed";
  if (s.examined.has(e.id)) return "rejected";
  return "unseen";
}

export function edgesGeoJSON(prep: Prepared, s: ViewState): FC {
  return {
    type: "FeatureCollection",
    features: prep.pairs.map((p) => {
      let st: Status = "unseen";
      let cur = false;
      for (const e of p.edges) {
        const es = edgeStatus(e, s);
        if (PRIORITY[es] > PRIORITY[st]) st = es;
        if (s.currentEdges.has(e.id)) cur = true;
      }
      return {
        type: "Feature",
        properties: { st, cur },
        geometry: { type: "LineString", coordinates: p.geometry },
      };
    }),
  };
}

export function labelsGeoJSON(prep: Prepared, s: ViewState): FC {
  return {
    type: "FeatureCollection",
    features: prep.pairs.map((p) => {
      const cur = p.edges.some((e) => s.currentEdges.has(e.id));
      return {
        type: "Feature",
        // prio : plus petit = placé en premier (donc jamais masqué par un autre texte)
        properties: { label: p.label, pen: p.penalized, cur, prio: cur ? 0 : p.penalized ? 1 : 2 },
        geometry: { type: "Point", coordinates: p.mid },
      };
    }),
  };
}

export function nodesGeoJSON(data: TraceData, prep: Prepared, s: ViewState): FC {
  return {
    type: "FeatureCollection",
    features: data.nodes.map((n) => {
      const d = s.dist.get(n.id);
      let st = "unseen";
      if (n.id === s.current) st = "current";
      else if (s.settled.has(n.id)) st = "settled";
      else if (d !== undefined) st = "frontier";
      const role = n.id === data.source ? "source" : n.id === data.target ? "target" : "";
      return {
        type: "Feature",
        properties: { st, role, lbl: d === undefined ? "" : fmt(d) },
        geometry: { type: "Point", coordinates: [n.lon, n.lat] },
      };
    }),
  };
}

/** Chemin final (en vert), seulement quand toutes les étapes ont été jouées. */
export function pathGeoJSON(data: TraceData, prep: Prepared, k: number): FC {
  const features: Feat[] = [];
  if (data.path && k >= data.steps.length) {
    const coords: Point[] = [];
    data.path.edges.forEach((id, i) => {
      const e = prep.edgeById.get(id);
      if (!e) return;
      coords.push(...(i === 0 ? e.geometry : e.geometry.slice(1)));
    });
    if (coords.length >= 2) {
      features.push({ type: "Feature", properties: {}, geometry: { type: "LineString", coordinates: coords } });
    }
  }
  return { type: "FeatureCollection", features };
}