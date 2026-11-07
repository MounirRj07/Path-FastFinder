"use client";

import { FormEvent, useEffect, useState } from "react";
import { ApiError, createPenalty, updatePenalty } from "@/lib/api";
import { PENALTY_LEVELS, type Penalty, type PenaltyLevel } from "@/lib/types";

interface Props {
  /** Tronçons sélectionnés sur la carte (ignorés en mode modification) */
  edgeIds: number[];
  streetName?: string | null;
  /** Si renseigné : le formulaire modifie cette pénalité (PATCH) */
  editing?: Penalty | null;
  onSaved: () => void;
  onCancelEdit?: () => void;
  /** Erreurs à traiter par la page (401, 403, réseau...) */
  onApiError: (err: unknown) => void;
}

const pad = (n: number) => String(n).padStart(2, "0");

/** ISO UTC -> valeur d'un <input type="datetime-local"> en heure locale */
function toLocalInput(iso: string | Date) {
  const d = new Date(iso);
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(
    d.getHours()
  )}:${pad(d.getMinutes())}`;
}

function defaultStart() {
  return toLocalInput(new Date());
}
function defaultEnd() {
  return toLocalInput(new Date(Date.now() + 24 * 3600 * 1000));
}

export default function PenaltyForm({
  edgeIds,
  streetName,
  editing,
  onSaved,
  onCancelEdit,
  onApiError,
}: Props) {
  const [level, setLevel] = useState<PenaltyLevel>("moyen");
  const [reason, setReason] = useState("");
  const [startsAt, setStartsAt] = useState(defaultStart);
  const [endsAt, setEndsAt] = useState(defaultEnd);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);

  // Remplit le formulaire quand on passe en mode modification
  useEffect(() => {
    if (editing) {
      setLevel(editing.level);
      setReason(editing.reason);
      setStartsAt(toLocalInput(editing.starts_at));
      setEndsAt(toLocalInput(editing.ends_at));
    } else {
      setLevel("moyen");
      setReason("");
      setStartsAt(defaultStart());
      setEndsAt(defaultEnd());
    }
    setErrors({});
  }, [editing]);

  function validate() {
    const e: Record<string, string> = {};
    if (!reason.trim()) e.reason = "Le motif est obligatoire.";
    if (!startsAt) e.starts_at = "La date de début est obligatoire.";
    if (!endsAt) e.ends_at = "La date de fin est obligatoire.";
    if (startsAt && endsAt && new Date(endsAt) <= new Date(startsAt)) {
      e.ends_at = "La date de fin doit être après la date de début.";
    }
    if (!editing && edgeIds.length === 0) {
      e.edge_ids = "Sélectionnez d'abord une route sur la carte.";
    }
    return e;
  }

  async function handleSubmit(ev: FormEvent) {
    ev.preventDefault();
    const e = validate();
    setErrors(e);
    if (Object.keys(e).length > 0) return;

    setSaving(true);
    try {
      // datetime-local = heure locale sans fuseau -> on envoie de l'UTC
      const common = {
        level,
        reason: reason.trim(),
        starts_at: new Date(startsAt).toISOString(),
        ends_at: new Date(endsAt).toISOString(),
      };
      if (editing) {
        await updatePenalty(editing.id, common);
      } else {
        await createPenalty({ edge_ids: edgeIds, ...common });
      }
      onSaved();
      if (!editing) {
        setReason("");
        setStartsAt(defaultStart());
        setEndsAt(defaultEnd());
      }
    } catch (err) {
      if (err instanceof ApiError && err.status === 422) {
        setErrors(err.fieldErrors); // erreurs de validation du serveur
      } else {
        onApiError(err);
      }
    } finally {
      setSaving(false);
    }
  }

  const fieldClass = "w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-black";
  const errorClass = "text-sm text-red-600";

  return (
    <form
      onSubmit={handleSubmit}
      noValidate
      className="space-y-3 rounded-xl border border-gray-300 p-4"
    >
      <h2 className="font-semibold">
        {editing ? "Modifier la pénalité" : "Nouvelle pénalité"}
      </h2>

      {!editing && (
        <p className="text-sm">
          {edgeIds.length > 0
            ? `${edgeIds.length} tronçon(s) sélectionné(s)${
                streetName ? ` : ${streetName}` : ""
              }`
            : "Aucune route sélectionnée."}
        </p>
      )}
      {errors.edge_ids && <p className={errorClass}>{errors.edge_ids}</p>}

      <div className="space-y-1">
        <label htmlFor="level" className="block text-sm font-medium">
          Niveau
        </label>
        <select
          id="level"
          value={level}
          onChange={(e) => setLevel(e.target.value as PenaltyLevel)}
          className={fieldClass}
        >
          {PENALTY_LEVELS.map((l) => (
            <option key={l.value} value={l.value}>
              {l.label} ({l.factor})
            </option>
          ))}
        </select>
        {errors.level && <p className={errorClass}>{errors.level}</p>}
      </div>

      <div className="space-y-1">
        <label htmlFor="reason" className="block text-sm font-medium">
          Motif
        </label>
        <input
          id="reason"
          type="text"
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          placeholder="Ex. : Travaux de voirie"
          className={fieldClass}
        />
        {errors.reason && <p className={errorClass}>{errors.reason}</p>}
      </div>

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <div className="space-y-1">
          <label htmlFor="starts_at" className="block text-sm font-medium">
            Début
          </label>
          <input
            id="starts_at"
            type="datetime-local"
            value={startsAt}
            onChange={(e) => setStartsAt(e.target.value)}
            className={fieldClass}
          />
          {errors.starts_at && <p className={errorClass}>{errors.starts_at}</p>}
        </div>
        <div className="space-y-1">
          <label htmlFor="ends_at" className="block text-sm font-medium">
            Fin
          </label>
          <input
            id="ends_at"
            type="datetime-local"
            value={endsAt}
            onChange={(e) => setEndsAt(e.target.value)}
            className={fieldClass}
          />
          {errors.ends_at && <p className={errorClass}>{errors.ends_at}</p>}
        </div>
      </div>

      <div className="flex gap-2">
        <button
          type="submit"
          disabled={saving}
          className="rounded-md bg-blue-600 px-4 py-2 font-medium text-white disabled:opacity-50"
        >
          {saving ? "Enregistrement..." : editing ? "Enregistrer" : "Ajouter"}
        </button>
        {editing && (
          <button
            type="button"
            onClick={onCancelEdit}
            className="rounded-md border px-4 py-2"
          >
            Annuler
          </button>
        )}
      </div>
    </form>
  );
}
