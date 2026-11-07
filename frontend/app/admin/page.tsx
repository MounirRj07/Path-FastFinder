"use client";

import { useCallback, useEffect, useState } from "react";
import dynamic from "next/dynamic";
import { useRouter } from "next/navigation";
import { ApiError, getNearestEdge, listPenalties } from "@/lib/api";
import { supabase } from "@/lib/supabase";
import { useAdminSession } from "@/lib/useAdminSession";
import type { NearestEdge, Penalty } from "@/lib/types";
import PenaltyForm from "@/components/admin/PenaltyForm";
import PenaltyList from "@/components/admin/PenaltyList";

// MapLibre ne fonctionne pas côté serveur : chargement client uniquement
const AdminMap = dynamic(() => import("@/components/admin/AdminMap"), {
  ssr: false,
  loading: () => (
    <div className="flex h-[420px] items-center justify-center rounded-xl border border-gray-300">
      Chargement de la carte...
    </div>
  ),
});

export default function AdminPage() {
  const router = useRouter();
  const { status, logout } = useAdminSession();
  const [penalties, setPenalties] = useState<Penalty[]>([]);
  const [editing, setEditing] = useState<Penalty | null>(null);
  const [forbidden, setForbidden] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Sélection d'une route sur la carte
  const [selection, setSelection] = useState<NearestEdge | null>(null);
  const [wholeWay, setWholeWay] = useState(false);
  const [lastClick, setLastClick] = useState<{ lat: number; lon: number } | null>(null);
  const [selecting, setSelecting] = useState(false);

  // Saisie manuelle des tronçons : solution de secours si la carte ne charge pas
  const [manualIds, setManualIds] = useState("");
  const manualEdgeIds = manualIds
    .split(",")
    .map((s) => s.trim())
    .filter((s) => s !== "")
    .map(Number)
    .filter((n) => Number.isInteger(n) && n >= 0);
  const edgeIds = selection ? selection.edge_ids : manualEdgeIds;

  // Gestion commune des erreurs d'API, passée aux composants enfants
  const handleApiError = useCallback(
    async (err: unknown) => {
      if (err instanceof ApiError) {
        if (err.isUnauthorized) {
          await supabase.auth.signOut();
          router.replace("/admin/login");
          return;
        }
        if (err.isForbidden) {
          setForbidden(true);
          return;
        }
        setError(err.message);
        return;
      }
      setError("Une erreur inattendue est survenue.");
    },
    [router]
  );

  const reload = useCallback(async () => {
    try {
      setError(null);
      setPenalties(await listPenalties());
    } catch (err) {
      await handleApiError(err);
    }
  }, [handleApiError]);

  useEffect(() => {
    if (status === "authenticated") reload();
  }, [status, reload]);

  const select = useCallback(
    async (lat: number, lon: number, whole: boolean) => {
      setSelecting(true);
      setError(null);
      try {
        setSelection(await getNearestEdge(lat, lon, whole));
      } catch (err) {
        await handleApiError(err);
      } finally {
        setSelecting(false);
      }
    },
    [handleApiError]
  );

  const handleMapClick = useCallback(
    (lat: number, lon: number) => {
      if (editing) return; // en modification, la sélection ne change pas
      setLastClick({ lat, lon });
      select(lat, lon, wholeWay);
    },
    [editing, wholeWay, select]
  );

  function clearSelection() {
    setSelection(null);
    setLastClick(null);
    setManualIds("");
  }

  if (status === "loading") {
    return <p className="p-6">Chargement...</p>;
  }

  if (forbidden) {
    return (
      <main className="space-y-4 p-6">
        <p role="alert" className="font-medium text-red-600">
          Accès réservé aux administrateurs.
        </p>
        <button onClick={logout} className="rounded-md border px-3 py-2">
          Se déconnecter
        </button>
      </main>
    );
  }

  return (
    <main className="space-y-6 p-6">
      <header className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">Tableau de bord des pénalités</h1>
        <button onClick={logout} className="rounded-md border px-3 py-2">
          Se déconnecter
        </button>
      </header>

      {error && (
        <p role="alert" className="text-red-600">
          {error}
        </p>
      )}

      <AdminMap
        penalties={penalties}
        selection={selection}
        onMapClick={handleMapClick}
      />

      <div className="flex flex-wrap items-center gap-4 text-sm">
        <label className="flex items-center gap-2">
          <input
            type="checkbox"
            checked={wholeWay}
            onChange={(e) => {
              setWholeWay(e.target.checked);
              if (lastClick) select(lastClick.lat, lastClick.lon, e.target.checked);
            }}
          />
          Toute la rue
        </label>

        <span>
          {selecting
            ? "Recherche du tronçon..."
            : selection
            ? `Sélection : ${selection.name || "rue sans nom"} (${selection.edge_ids.length} tronçon${
                selection.edge_ids.length > 1 ? "s" : ""
              })`
            : "Cliquez sur une route de la carte pour la sélectionner."}
        </span>

        {selection && (
          <button onClick={clearSelection} className="rounded-md border px-2 py-1">
            Effacer la sélection
          </button>
        )}
      </div>

      <div className="grid gap-6 lg:grid-cols-[minmax(0,24rem)_1fr]">
        <div className="space-y-4">
          {!editing && !selection && (
            <details className="rounded-xl border border-dashed border-gray-400 p-3 text-sm">
              <summary className="cursor-pointer font-medium">
                Saisie manuelle des tronçons (secours)
              </summary>
              <input
                value={manualIds}
                onChange={(e) => setManualIds(e.target.value)}
                placeholder="10432, 10433"
                aria-label="Identifiants de tronçons"
                className="mt-2 w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-black"
              />
            </details>
          )}

          <PenaltyForm
            edgeIds={edgeIds}
            editing={editing}
            onSaved={() => {
              setEditing(null);
              clearSelection();
              reload();
            }}
            onCancelEdit={() => setEditing(null)}
            onApiError={handleApiError}
          />
        </div>

        <PenaltyList
          penalties={penalties}
          onEdit={setEditing}
          onChanged={reload}
          onApiError={handleApiError}
        />
      </div>
    </main>
  );
}
