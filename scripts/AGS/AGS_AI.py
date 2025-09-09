# scripts/AGS/AGS_AI.py

import json
import os
import re
import sys
import requests
from bs4 import BeautifulSoup
from googlesearch import search
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
FICHIER_ENTREPRISE = os.path.join(REPO_ROOT, "config", "parametres_entreprise.json")

SEARCH_QUERY = "taux cotisation AGS employeur URSSAF 2025"
USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"


def _read_est_ett(path: str) -> bool:
    """Lit le flag ETT depuis parametres_entreprise.json; False si absent."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        return bool(
            cfg.get("PARAMETRES_ENTREPRISE", {})
            .get("conditions_cotisations", {})
            .get("est_entreprise_travail_temporaire", False)
        )
    except Exception:
        return False


def _extract_json_with_gpt(page_text: str) -> dict | None:
    """
    Demande à l'IA d'extraire les pourcentages AGS (général et ETT) en JSON.
    Retour attendu (exemple):
    {
      "general_percent": 0.25,
      "ett_percent": 0.30
    }
    (valeurs en POURCENT, pas en taux)
    """
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return None

    client = OpenAI()

    prompt = """
Tu es un extracteur. Lis le texte suivant (copie brute d'une page web française sur les cotisations).
Si tu trouves le taux de la "Cotisation AGS" (employeurs), renvoie un JSON STRICT du format :

{
  "general_percent": <nombre ou null>,  // taux en POURCENT pour le cas général (ex: 0.25 pour 0,25%)
  "ett_percent": <nombre ou null>       // taux en POURCENT pour les entreprises de travail temporaire (ETT), sinon null
}

Règles :
- Utilise le point comme séparateur décimal.
- Si une seule valeur AGS est présente, mets-la dans "general_percent" et laisse "ett_percent" à null,
  sauf si le texte indique explicitement que cette valeur est celle des ETT.
- Si rien n'est trouvé, renvoie {"general_percent": null, "ett_percent": null}.
Texte :
---
""" + page_text

    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            response_format={"type": "json_object"},
            temperature=0,
            messages=[
                {"role": "system", "content": "Tu rends uniquement du JSON valide."},
                {"role": "user", "content": prompt},
            ],
        )
        content = resp.choices[0].message.content.strip()
        return json.loads(content)
    except Exception:
        return None


def _get_page_text(url: str) -> str | None:
    try:
        res = requests.get(url, timeout=20, headers={"User-Agent": USER_AGENT})
        res.raise_for_status()
        soup = BeautifulSoup(res.text, "html.parser")
        return soup.get_text(" ", strip=True)
    except Exception:
        return None


def get_ags_payload_via_ai(est_ett: bool) -> dict:
    """
    Cherche sur le web, extrait via IA, et renvoie un payload standardisé :
    {
      "id": "ags",
      "type": "cotisation",
      "libelle": "Cotisation AGS",
      "base": "brut",
      "valeurs": {"salarial": null, "patronal": <taux ou null>},
      "meta": {
        "source": [{"url": "<dernière URL analysée>", "label": "IA (Google+OpenAI)", "date_doc": ""}],
        "generator": "AGS_AI.py"
      }
    }
    """
    sources = []
    chosen_rate = None
    try:
        results = list(search(SEARCH_QUERY, num_results=5, lang="fr"))
    except Exception:
        results = []

    # Prioriser URSSAF
    results_sorted = sorted(results, key=lambda u: (0 if "urssaf.fr" in u else 1, u))

    for url in results_sorted:
        text = _get_page_text(url)
        if not text:
            continue

        # Petite coupe pour éviter des prompts trop longs
        page_text = text[:12000]
        data = _extract_json_with_gpt(page_text) or {}

        # data attendu : {"general_percent": x or null, "ett_percent": y or null}
        gen_p = data.get("general_percent", None)
        ett_p = data.get("ett_percent", None)

        # Choix selon configuration ETT
        if est_ett and ett_p is not None:
            chosen_rate = round(float(ett_p) / 100.0, 6)
        elif gen_p is not None:
            chosen_rate = round(float(gen_p) / 100.0, 6)
        elif ett_p is not None:
            # fallback si seul ETT connu
            chosen_rate = round(float(ett_p) / 100.0, 6)

        sources = [{"url": url, "label": "IA (Google+OpenAI)", "date_doc": ""}]
        if chosen_rate is not None:
            break

    payload = {
        "id": "ags",
        "type": "cotisation",
        "libelle": "Cotisation AGS",
        "base": "brut",
        "valeurs": {"salarial": None, "patronal": chosen_rate},
        "meta": {
            "source": sources or [{"url": "", "label": "IA (Google+OpenAI)", "date_doc": ""}],
            "generator": "AGS_AI.py",
        },
    }
    return payload


if __name__ == "__main__":
    est_ett = _read_est_ett(FICHIER_ENTREPRISE)
    payload = get_ags_payload_via_ai(est_ett)
    print(json.dumps(payload, ensure_ascii=False))
