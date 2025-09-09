# scripts/CSG/CSG_AI.py

import json
import os
import requests
from bs4 import BeautifulSoup
from openai import OpenAI
from googlesearch import search
from dotenv import load_dotenv
from datetime import datetime, timezone

load_dotenv()

# --- Config ---
SEARCH_QUERY = "taux csg crds salarié urssaf 2025"


def iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def extract_json_with_gpt(page_text: str, prompt: str) -> dict | None:
    """
    Interroge GPT-4o-mini et s'attend à recevoir une chaîne JSON valide.
    Aucune sortie annexe. Retourne un dict ou None.
    """
    if not os.getenv("OPENAI_API_KEY"):
        return None
    try:
        client = OpenAI()
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": "Tu es un expert en extraction de données qui répond au format JSON."},
                {"role": "user", "content": prompt},
            ],
            temperature=0,
        )
        return json.loads(resp.choices[0].message.content.strip())
    except Exception:
        return None


def get_taux_csg_crds_via_ai() -> tuple[dict | None, str | None]:
    """
    Orchestre: recherche Google -> scrap texte -> extraction IA -> calcul taux.
    Retourne ({'deductible': float, 'non_deductible': float}, source_url) ou (None, None).
    """
    prompt_template = """
    Analyse le texte suivant de la section "Taux de cotisations salarié" et extrais les 3 taux suivants :
    1. Le taux de la "CSG imposable".
    2. Le taux de la "CSG non imposable" (qui est la part déductible).
    3. Le taux de la "CRDS".

    Retourne le résultat dans un objet JSON valide et minifié.
    Les clés doivent être "csg_imposable", "csg_non_imposable", "crds".

    Ne fournis AUCUNE explication, juste le JSON. Le format doit être EXACTEMENT comme suit :
    {"csg_imposable":2.40,"csg_non_imposable":6.80,"crds":0.50}

    Voici le texte à analyser :
    ---
    """.strip()

    try:
        search_results = list(search(SEARCH_QUERY, num_results=50, lang="fr"))
    except Exception:
        return None, None
    if not search_results:
        return None, None

    for page_url in search_results:
        try:
            r = requests.get(page_url, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
            r.raise_for_status()
            soup = BeautifulSoup(r.text, "html.parser")
            page_text = soup.get_text(" ", strip=True)

            final_prompt = prompt_template + "\n" + page_text[:12000]
            data = extract_json_with_gpt(page_text, final_prompt)
            if not data or not all(k in data for k in ("csg_imposable", "csg_non_imposable", "crds")):
                continue

            # Convertit % -> taux décimal
            try:
                deductible = round(float(data["csg_non_imposable"]) / 100.0, 5)
                non_deductible = round((float(data["csg_imposable"]) + float(data["crds"])) / 100.0, 5)
            except Exception:
                continue

            return {"deductible": deductible, "non_deductible": non_deductible}, page_url
        except Exception:
            continue

    return None, None


def build_payload(taux: dict | None, source_url: str | None) -> dict:
    vals = {"salarial": None, "patronal": None}
    if taux is not None:
        vals["salarial"] = {
            "deductible": taux.get("deductible"),
            "non_deductible": taux.get("non_deductible"),
        }
    return {
        "id": "csg",
        "type": "cotisation",
        "libelle": "CSG/CRDS",
        "base": "brut",
        "valeurs": vals,
        "meta": {
            "source": [{"url": source_url or "", "label": "", "date_doc": ""}],
            "scraped_at": iso_now(),
            "generator": "scripts/CSG/CSG_AI.py",
            "method": "ai",
        },
    }


if __name__ == "__main__":
    taux, url = get_taux_csg_crds_via_ai()
    payload = build_payload(taux, url)
    print(json.dumps(payload, ensure_ascii=False))
