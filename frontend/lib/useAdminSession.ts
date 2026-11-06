"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import type { Session } from "@supabase/supabase-js";
import { supabase } from "./supabase";

type Status = "loading" | "authenticated";

/**
 * Protège une page admin côté client :
 * - pas de session Supabase -> redirection vers /admin/login
 * - session présente -> renvoie la session
 *
 * Attention : ce n'est qu'un confort d'affichage. La vraie sécurité est le
 * 401/403 renvoyé par l'API (voir handleAuthError dans la page).
 */
export function useAdminSession() {
  const router = useRouter();
  const [session, setSession] = useState<Session | null>(null);
  const [status, setStatus] = useState<Status>("loading");

  useEffect(() => {
    let active = true;

    supabase.auth.getSession().then(({ data }) => {
      if (!active) return;
      if (!data.session) {
        router.replace("/admin/login");
      } else {
        setSession(data.session);
        setStatus("authenticated");
      }
    });

    // Réagit à la déconnexion ou à l'expiration de la session
    const { data: listener } = supabase.auth.onAuthStateChange((_event, s) => {
      if (!active) return;
      if (!s) router.replace("/admin/login");
      else setSession(s);
    });

    return () => {
      active = false;
      listener.subscription.unsubscribe();
    };
  }, [router]);

  const logout = async () => {
    await supabase.auth.signOut();
    router.replace("/admin/login");
  };

  return { session, status, logout };
}
