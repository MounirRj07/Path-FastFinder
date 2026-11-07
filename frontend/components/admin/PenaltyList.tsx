"use client";

import { useState } from "react";
import { deletePenalty } from "@/lib/api";
import {
  PENALTY_LEVELS,
  getPenaltyStatus,
  type Penalty,
  type PenaltyStatus,
} from "@/lib/types";

type Filter = "all" | PenaltyStatus;

const FILTERS: { value: Filter; label: string }[] = [
  { value: "active", label: "Actives" },
  { value: "upcoming", label: "À venir" },
  { value: "past", label: "Passées" },
  { value: "all", label: "Toutes" },
];

const STATUS_LABEL: Record<PenaltyStatus, string> = {
  active: "Active",
  upcoming: "À venir",
  past: "Passée",
};

const fmt = (iso: string) =>
  new Date(iso).toLocaleString("fr-FR", {
    dateStyle: "short",
    timeStyle: "short",
  });

interface Props {
  penalties: Penalty[];
  onEdit: (p: Penalty) => void;
  /** Appelé après un retrait réussi : la page recharge la liste */
  onChanged: () => void;
  onApiError: (err: unknown) => void;
}

export default function PenaltyList({
  penalties,
  onEdit,
  onChanged,
  onApiError,
}: Props) {
  const [filter, setFilter] = useState<Filter>("active");
  const [confirmingId, setConfirmingId] = useState<number | null>(null);
  const [busyId, setBusyId] = useState<number | null>(null);

  const visible = penalties.filter(
    (p) => filter === "all" || getPenaltyStatus(p) === filter
  );

  async function handleDelete(id: number) {
    setBusyId(id);
    try {
      await deletePenalty(id);
      setConfirmingId(null);
      onChanged();
    } catch (err) {
      onApiError(err);
    } finally {
      setBusyId(null);
    }
  }

  return (
    <section className="space-y-3">
      <div className="flex flex-wrap gap-2" role="tablist">
        {FILTERS.map((f) => (
          <button
            key={f.value}
            role="tab"
            aria-selected={filter === f.value}
            onClick={() => setFilter(f.value)}
            className={`rounded-full border px-3 py-1 text-sm ${
              filter === f.value ? "bg-blue-600 text-white" : ""
            }`}
          >
            {f.label}
          </button>
        ))}
      </div>

      {visible.length === 0 ? (
        <p className="text-sm">Aucune pénalité dans cette catégorie.</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="border-b">
                <th className="py-2 pr-3">Rue</th>
                <th className="py-2 pr-3">Niveau</th>
                <th className="py-2 pr-3">Motif</th>
                <th className="py-2 pr-3">Début</th>
                <th className="py-2 pr-3">Fin</th>
                <th className="py-2 pr-3">État</th>
                <th className="py-2">Actions</th>
              </tr>
            </thead>
            <tbody>
              {visible.map((p) => {
                const level = PENALTY_LEVELS.find((l) => l.value === p.level);
                return (
                  <tr key={p.id} className="border-b align-top">
                    <td className="py-2 pr-3">
                      {p.street_name ?? "(rue sans nom)"}
                    </td>
                    <td className="py-2 pr-3">
                      <span
                        className="inline-block rounded px-2 py-0.5 text-white"
                        style={{ backgroundColor: level?.color ?? "#6b7280" }}
                      >
                        {level?.label ?? p.level}
                      </span>
                    </td>
                    <td className="py-2 pr-3">{p.reason}</td>
                    <td className="py-2 pr-3">{fmt(p.starts_at)}</td>
                    <td className="py-2 pr-3">{fmt(p.ends_at)}</td>
                    <td className="py-2 pr-3">
                      {STATUS_LABEL[getPenaltyStatus(p)]}
                    </td>
                    <td className="py-2">
                      {confirmingId === p.id ? (
                        // Confirmation dans l'interface (pas de window.confirm)
                        <div className="flex flex-wrap items-center gap-2">
                          <span>Retirer ?</span>
                          <button
                            onClick={() => handleDelete(p.id)}
                            disabled={busyId === p.id}
                            className="rounded-md bg-red-600 px-2 py-1 text-white disabled:opacity-50"
                          >
                            {busyId === p.id ? "..." : "Oui"}
                          </button>
                          <button
                            onClick={() => setConfirmingId(null)}
                            className="rounded-md border px-2 py-1"
                          >
                            Non
                          </button>
                        </div>
                      ) : (
                        <div className="flex gap-2">
                          <button
                            onClick={() => onEdit(p)}
                            className="rounded-md border px-2 py-1"
                          >
                            Modifier
                          </button>
                          <button
                            onClick={() => setConfirmingId(p.id)}
                            className="rounded-md border border-red-600 px-2 py-1 text-red-600"
                          >
                            Retirer
                          </button>
                        </div>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
