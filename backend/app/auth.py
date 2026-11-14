"""
Authentification : jeton Supabase valide, puis rôle admin dans la table profiles.
"""

import os

import httpx
import psycopg
from fastapi import Depends, Header, HTTPException


def current_user_id(authorization: str | None = Header(default=None)) -> str:
    supabase_url = os.environ.get("SUPABASE_URL")
    anon_key = os.environ.get("SUPABASE_ANON_KEY")
    if not supabase_url or not anon_key:
        raise HTTPException(status_code=500, detail="SUPABASE_URL ou SUPABASE_ANON_KEY manquant")
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Connexion requise")

    r = httpx.get(
        f"{supabase_url}/auth/v1/user",
        headers={"Authorization": authorization, "apikey": anon_key},
        timeout=10,
    )
    if r.status_code != 200:
        raise HTTPException(status_code=401, detail="Jeton invalide ou expiré")
    return r.json()["id"]


def require_admin(user_id: str = Depends(current_user_id)) -> str:
    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        row = conn.execute(
            "select role from profiles where user_id = %s::uuid", (user_id,)
        ).fetchone()
    if not row or row[0] != "admin":
        raise HTTPException(status_code=403, detail="Accès réservé aux administrateurs")
    return user_id