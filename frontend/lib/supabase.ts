import { createClient } from "@supabase/supabase-js";
import { MOCK, mockSupabase } from "./mock";

// En mode démo (NEXT_PUBLIC_MOCK=true), on remplace Supabase par une fausse
// authentification locale : aucun appel réseau, aucune clé nécessaire.
export const supabase = MOCK
  ? (mockSupabase as unknown as ReturnType<typeof createClient>)
  : createClient(
      process.env.NEXT_PUBLIC_SUPABASE_URL!,
      process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!
    );
