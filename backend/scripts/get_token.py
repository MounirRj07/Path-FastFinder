import os
from getpass import getpass

import httpx
from dotenv import load_dotenv

load_dotenv()
email = input("E-mail : ")
mot_de_passe = getpass("Mot de passe : ")

r = httpx.post(
    f"{os.environ['SUPABASE_URL']}/auth/v1/token?grant_type=password",
    headers={"apikey": os.environ["SUPABASE_ANON_KEY"]},
    json={"email": email, "password": mot_de_passe},
    timeout=15,
)
print("Statut :", r.status_code)
print(r.json().get("access_token", r.text))