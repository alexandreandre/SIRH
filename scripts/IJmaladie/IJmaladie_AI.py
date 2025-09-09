# scripts/IJmaladie/IJmaladie_AI.py
import json
import os
from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from googlesearch import search
from openai import OpenAI

load_dotenv()

SEARCH_QUERY = "montants maximum indemnités journalières ameli 2025"

def iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def extract_json_with_gpt(page_text: str) -> dict | None:
    """Interroge GPT-4o-mini et renvoie un objet dict avec les 4 plafonds."""
    if not os.getenv("OPENAI_API_KEY"):
        return None
    client = OpenAI()
    prompt = (
        "Analyse le texte suivant et extrais les 4 montants maximums des indemnités journalières pour 2025.\n"
        'Les clés doivent être "maladie", "maternite_paternite", "at_mp", et "at_mp_majoree".\n'
        "Les valeurs doivent être des nombres.\n\n"
        "Le format de sortie DOIT être un JSON minifié. Ne fournis AUCUNE explication.\n\n"
        'Exemple de format attendu : {"maladie":41.47,"maternite_paternite":101.94,"at_mp":235.69,"at_mp_majoree":314.25}\n\n'
        "Voici le texte :\n---\n" + page_text[:12000]
    )
    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": "Tu es un expert en extraction de données qui répond au format JSON."},
                {"role": "user", "content": prompt},
            ],
            temperature=0,
        )
        extracted = resp.choices[0].message.content.strip()
        return json.loads(extracted)
    except Exception:
        return None

def get_all_plafonds_ij_via_ai() -> tuple[dict | None, str | None]:
    """Cherche sur Google et renvoie (data_dict, source_url) si JSON complet trouvé."""
    try:
        search_results = list(search(SEARCH_QUERY, num_results=50, lang="fr"))
    except Exception:
        return None, None
    if not search_results:
        return None, None

    expected_keys = {"maladie", "maternite_paternite", "at_mp", "at_mp_majoree"}
    for page_url in search_results:
        try:
            r = requests.get(page_url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
            r.raise_for_status()
            soup = BeautifulSoup(r.text, "html.parser")
            page_text = soup.get_text(" ", strip=True)
            if not page_text:
                continue
            data = extract_json_with_gpt(page_text)
            if isinstance(data, dict) and expected_keys.issubset(data.keys()):
                return data, page_url
        except Exception:
            continue
    return None, None

def build_payload(vals: dict | None, source_url: str | None) -> dict:
    valeurs = {
        "maladie": None,
        "maternite_paternite": None,
        "at_mp": None,
        "at_mp_majoree": None,
        "unite": "EUR/jour",
    }
    if vals:
        valeurs.update({
            "maladie": vals.get("maladie"),
            "maternite_paternite": vals.get("maternite_paternite"),
            "at_mp": vals.get("at_mp"),
            "at_mp_majoree": vals.get("at_mp_majoree"),
        })
    return {
        "id": "ij_maladie",
        "type": "secu",
        "libelle": "Indemnités journalières — montants maximums",
        "base": None,
        "valeurs": valeurs,
        "meta": {
            "source": ([{"url": source_url, "label": "Web + IA", "date_doc": ""}] if source_url else []),
            "scraped_at": iso_now(),
            "generator": "scripts/IJmaladie/IJmaladie_AI.py",
            "method": "ai",
        },
    }

def main() -> None:
    vals, src = get_all_plafonds_ij_via_ai()
    payload = build_payload(vals, src)
    print(json.dumps(payload, ensure_ascii=False))

if __name__ == "__main__":
    main()
