"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { ApiError, listPenalties } from "@/lib/api";
import { supabase } from "@/lib/supabase";
import { useAdminSession } from "@/lib/useAdminSession";
import type { Penalty } from "@/lib/types";
import PenaltyForm from "@/components/admin/PenaltyForm";
import PenaltyList from "@/components/admin/PenaltyList";

export default function AdminPage() {
  const router = useRouter();
  const { status, logout } = useAdminSession();

  const [penalties, setPenalties] = useState<Penalty[]>([]);
  const [editing, setEditing] = useState<Penalty | null>(null);
  const [forbidden, setForbidden] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // PROVISOIRE : saisie manuelle des tronçons, en attendant la carte d'Elnis.
  // Quand MapView sera là, ces ids viendront de getNearestEdge().
  const [manualEdges, setManualEdges] = useState("");
  const edgeIds = manualEdges
    .split(",")
    .map((s) => s.trim())
    .filter((s) => s !== "")
    .map(Number)
    .filter((n) => Number.isInteger(n) && n >= 0);

  // Gestion commune des erreurs d'API
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
      handleApiError(err);
    }
  }, [handleApiError]);

  useEffect(() => {
    if (status === "authenticated") reload();
  }, [status, reload]);

  if (status === "loading") return <p className="p-6">Chargement...</p>;

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
    <main className="mx-auto max-w-5xl space-y-6 p-6">
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

      {/* Provisoire : remplacé par la carte avec sélection de route */}
      {!editing && (
        <div className="space-y-1 rounded-xl border border-dashed border-gray-400 p-4">
          <label htmlFor="manual" className="block text-sm font-medium">
            Identifiants de tronçons (provisoire, séparés par des virgules)
          </label>
          <input
            id="manual"
            value={manualEdges}
            onChange={(e) => setManualEdges(e.target.value)}
            placeholder="10432, 10433"
            className="w-full rounded-md border border-gray-300 px-3 py-2 text-black"
          />
        </div>
      )}

      <PenaltyForm
        edgeIds={edgeIds}
        editing={editing}
        onSaved={() => {
          setEditing(null);
          reload();
        }}
        onCancelEdit={() => setEditing(null)}
        onApiError={handleApiError}
      />

      <PenaltyList
        penalties={penalties}
        onEdit={setEditing}
        onChanged={reload}
        onApiError={handleApiError}
      />
    </main>
  );
}
