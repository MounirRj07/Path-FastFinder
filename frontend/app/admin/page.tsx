"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { ApiError, listPenalties } from "@/lib/api";
import { supabase } from "@/lib/supabase";
import { useAdminSession } from "@/lib/useAdminSession";
import type { Penalty } from "@/lib/types";

export default function AdminPage() {
  const router = useRouter();
  const { status, logout } = useAdminSession();
  const [penalties, setPenalties] = useState<Penalty[]>([]);
  const [forbidden, setForbidden] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleAuthError(err: unknown) {
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
  }

  useEffect(() => {
    if (status !== "authenticated") return;
    listPenalties().then(setPenalties).catch(handleAuthError);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [status]);

  if (status === "loading") {
    return <p className="p-6">Chargement...</p>;
  }

  if (forbidden) {
    return (
      <main className="p-6 space-y-4">
        <p role="alert" className="text-red-600 font-medium">
          Accès réservé aux administrateurs.
        </p>
        <button onClick={logout} className="rounded-md border px-3 py-2">
          Se déconnecter
        </button>
      </main>
    );
  }

  return (
    <main className="p-6 space-y-4">
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

      <p>{penalties.length} pénalité(s) chargée(s).</p>
    </main>
  );
}
