# scripts/Avantages/Avantages_AI.py

import json
import os
import sys
import requests
from bs4 import BeautifulSoup
from googlesearch import search
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

SEARCH_QUERY = "barème avantages en nature actuel"
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"

def make_payload(repas, titre_restaurant, logement_bareme, source_url=None):
    return {
        "id": "avantages_en_nature",
        "type": "param_bundle",
        "items": [
            {"key": "repas_valeur_forfaitaire_eur", "value": repas},
            {"key": "titre_restaurant_exoneration_max_eur", "value": titre_restaurant},
            {"key": "logement_bareme_forfaitaire", "value": logement_bareme},
        ],
        "meta": {
            "source": ([{"url": source_url, "label": "Source détectée par IA", "date_doc": ""}] if source_url else []),
            "generator": "scripts/Avantages/Avantages_AI.py",
        },
    }

def extract_json_with_gpt(page_text: str, prompt: str):
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return None
    try:
        client = OpenAI(api_key=api_key)
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": "Tu es un expert en extraction de données qui répond en JSON strict."},
                {"role": "user", "content": prompt}
            ],
            temperature=0,
        )
        return json.loads(resp.choices[0].message.content.strip())
    except Exception:
        return None

def normalize_number(v):
    if v is None:
        return None
    try:
        # accepte "7,26" ou "7.26" ou nombres
        if isinstance(v, str):
            v = v.replace("\u202f","").replace("\xa0","").replace("€","").replace(" ", "").replace(",", ".")
        return float(v)
    except Exception:
        return None

def normalize_bareme(lst):
    out = []
    if not isinstance(lst, list):
        return out
    for obj in lst:
        if not isinstance(obj, dict):
            continue
        rem_max = normalize_number(obj.get("remuneration_max"))
        v1 = normalize_number(obj.get("valeur_1_piece"))
        vpp = normalize_number(obj.get("valeur_par_piece"))
        if v1 is None or vpp is None:
            continue
        out.append({
            "remuneration_max_eur": rem_max if rem_max is not None else 9_999_999.99,
            "valeur_1_piece_eur": v1,
            "valeur_par_piece_suppl_eur": vpp,
        })
    return out

def get_avantages_via_ai():
    prompt_template = """
Analyse le texte suivant et extrais les 3 informations pour 2025. Retourne UNIQUEMENT un JSON minifié:
{"repas":..,"titre_restaurant":..,"logement":[{"remuneration_max":..,"valeur_1_piece":..,"valeur_par_piece":},{"remuneration_max":2354.99,"valeur_1_piece":91.80,"valeur_par_piece":58.90},{"remuneration_max":2747.49,"valeur_1_piece":104.80,"valeur_par_piece":78.70},{"remuneration_max":3532.49,"valeur_1_piece":117.90,"valeur_par_piece":98.20},{"remuneration_max":4317.49,"valeur_1_piece":144.50,"valeur_par_piece":124.50},{"remuneration_max":5102.49,"valeur_1_piece":170.40,"valeur_par_piece":150.40},{"remuneration_max":5887.49,"valeur_1_piece":196.80,"valeur_par_piece":183.30},{"remuneration_max":999999.99,"valeur_1_piece":222.70,"valeur_par_piece":209.60}]}
- "repas": valeur forfaitaire d'1 repas (en euros, nombre).
- "titre_restaurant": exonération maximale de la part patronale d'un titre-restaurant (en euros, nombre).
- "logement": barème complet, chaque objet avec "remuneration_max","valeur_1_piece","valeur_par_piece" (euros).
Aucune explication hors JSON.

Texte:
---
"""

    try:
        results = list(search(SEARCH_QUERY, num_results=50, lang="fr"))
    except Exception:
        results = []

    for url in results:
        try:
            r = requests.get(url, timeout=20, headers={"User-Agent": UA})
            r.raise_for_status()
            soup = BeautifulSoup(r.text, "html.parser")
            txt = soup.get_text(" ", strip=True)

            data = extract_json_with_gpt(txt[:15000], prompt_template + txt[:15000])
            if not data:
                continue

            repas = normalize_number(data.get("repas"))
            titre = normalize_number(data.get("titre_restaurant"))
            logement = normalize_bareme(data.get("logement"))

            if repas is not None and titre is not None and logement and len(logement) >= 3:
                return repas, titre, logement, url
        except Exception:
            continue
    return None, None, [], None

if __name__ == "__main__":
    repas, titre, logement, src = get_avantages_via_ai()
    payload = make_payload(repas, titre, logement, src)
    ok = payload["items"][0]["value"] is not None \
         and payload["items"][1]["value"] is not None \
         and isinstance(payload["items"][2]["value"], list) and len(payload["items"][2]["value"]) > 0
    print(json.dumps(payload, ensure_ascii=False))
    sys.exit(0 if ok else 2)
