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

  // PROVISOIRE : en attendant la carte d'Elnis (MapView), on saisit à la main
  // les identifiants de tronçons, par exemple "10432, 10433". À supprimer
  // quand la sélection sur la carte sera branchée.
  const [testIds, setTestIds] = useState("");
  const edgeIds = testIds
    .split(",")
    .map((s) => s.trim())
    .filter((s) => s !== "")
    .map(Number)
    .filter((n) => Number.isInteger(n) && n >= 0);

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

      <div className="grid gap-6 lg:grid-cols-[minmax(0,24rem)_1fr]">
        <div className="space-y-4">
          {/* Provisoire : à remplacer par la carte (sélection d'une route) */}
          {!editing && (
            <div className="space-y-1 rounded-xl border border-dashed border-gray-400 p-3">
              <label htmlFor="test-ids" className="block text-sm font-medium">
                IDs de tronçons (test, en attendant la carte)
              </label>
              <input
                id="test-ids"
                value={testIds}
                onChange={(e) => setTestIds(e.target.value)}
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
