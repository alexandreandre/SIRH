# scripts/AGIRC-ARRCO/AGIRC-ARRCO_AI.py

import json
import os
import sys
import requests
from bs4 import BeautifulSoup
from googlesearch import search
from openai import OpenAI
from dotenv import load_dotenv
from typing import Dict, Optional

load_dotenv()

SEARCH_QUERY = "agirc-arrco calcul des cotisations de retraite complémentaire 2025"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"

EXPECTED_KEYS = [
    "retraite_comp_t1_salarial", "retraite_comp_t1_patronal",
    "retraite_comp_t2_salarial", "retraite_comp_t2_patronal",
    "ceg_t1_salarial", "ceg_t1_patronal",
    "ceg_t2_salarial", "ceg_t2_patronal",
    "cet_salarial", "cet_patronal",
    "apec_salarial", "apec_patronal"
]

PROMPT_TEMPLATE = """
Tu es un extracteur de données. Analyse ce texte de page d'information AGIRC-ARRCO.
Objectif: retourner EXACTEMENT ce JSON (noms de clés identiques), avec les valeurs en POURCENT (ex: 3,15% -> 3.15).
Ne renvoie rien d'autre que du JSON valide.

{
  "retraite_comp_t1_salarial": 3.15,
  "retraite_comp_t1_patronal": 4.72,
  "retraite_comp_t2_salarial": 8.64,
  "retraite_comp_t2_patronal": 12.95,
  "ceg_t1_salarial": 0.86,
  "ceg_t1_patronal": 1.29,
  "ceg_t2_salarial": 1.08,
  "ceg_t2_patronal": 1.62,
  "cet_salarial": 0.14,
  "cet_patronal": 0.21,
  "apec_salarial": 0.024,
  "apec_patronal": 0.036
}

Rappels:
- Tranche 1 et Tranche 2 pour la retraite complémentaire.
- CEG Tranche 1 et Tranche 2.
- CET (une seule paire).
- APEC (une seule paire).
Si une valeur est introuvable, mets null. Texte à analyser:
---
"""

def _percent_to_rate(v: Optional[float]) -> Optional[float]:
    try:
        if v is None:
            return None
        return round(float(v) / 100.0, 5)
    except Exception:
        return None

def _ask_ai(page_text: str) -> Optional[Dict[str, float]]:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("[IA] OPENAI_API_KEY manquant.", file=sys.stderr)
        return None
    try:
        client = OpenAI()
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": "Assistant d'extraction. Réponds en JSON strict."},
                {"role": "user", "content": PROMPT_TEMPLATE + page_text[:12000]}
            ],
            temperature=0
        )
        raw = resp.choices[0].message.content.strip()
        data = json.loads(raw)
        # Validation des clés
        if not all(k in data for k in EXPECTED_KEYS):
            return None
        # Conversion % -> taux réels
        return {k: _percent_to_rate(data[k]) for k in EXPECTED_KEYS}
    except Exception as e:
        print(f"[IA] Erreur: {e}", file=sys.stderr)
        return None

def _mk_item(_id: str, libelle: str, base: str, sal: Optional[float], pat: Optional[float], source_url: str) -> Dict:
    return {
        "id": _id,
        "type": "cotisation",
        "libelle": libelle,
        "base": base,
        "valeurs": {"salarial": sal, "patronal": pat}
    }

def run() -> Dict:
    items = []
    best_url = ""
    try:
        results = list(search(SEARCH_QUERY, num_results=50, lang="fr"))
    except Exception as e:
        print(f"[AI] Recherche Google échouée: {e}", file=sys.stderr)
        results = []

    for url in results:
        try:
            r = requests.get(url, timeout=25, headers={"User-Agent": UA})
            r.raise_for_status()
            soup = BeautifulSoup(r.text, "html.parser")
            txt = soup.get_text(" ", strip=True)
            data = _ask_ai(txt)
            # on exige que toutes les valeurs existent et ne soient pas None
            if data and all(data.get(k) is not None for k in EXPECTED_KEYS):
                best_url = url
                items = [
                    _mk_item("retraite_comp_t1", "Retraite Complémentaire Tranche 1 (AGIRC-ARRCO)", "plafond_ss",
                             data["retraite_comp_t1_salarial"], data["retraite_comp_t1_patronal"], best_url),
                    _mk_item("retraite_comp_t2", "Retraite Complémentaire Tranche 2 (AGIRC-ARRCO)", "tranche_2",
                             data["retraite_comp_t2_salarial"], data["retraite_comp_t2_patronal"], best_url),
                    _mk_item("ceg_t1", "Contribution d'Équilibre Général (CEG) T1", "plafond_ss",
                             data["ceg_t1_salarial"], data["ceg_t1_patronal"], best_url),
                    _mk_item("ceg_t2", "Contribution d'Équilibre Général (CEG) T2", "tranche_2",
                             data["ceg_t2_salarial"], data["ceg_t2_patronal"], best_url),
                    _mk_item("cet", "Contribution d'Équilibre Technique (CET)", "brut_sup_plafond",
                             data["cet_salarial"], data["cet_patronal"], best_url),
                    _mk_item("apec", "Cotisation APEC (Cadres)", "brut_cadre_4_plafonds",
                             data["apec_salarial"], data["apec_patronal"], best_url),
                ]
                break
        except Exception:
            continue

    return {
        "id": "agirc_arrco_bundle",
        "type": "cotisation_bundle",
        "items": items,
        "meta": {
            "source": ([{"url": best_url, "label": "Page détectée par IA", "date_doc": ""}] if best_url else []),
            "generator": "scripts/AGIRC-ARRCO/AGIRC-ARRCO_AI.py",
        },
    }

if __name__ == "__main__":
    bundle = run()
    print(json.dumps(bundle, ensure_ascii=False))
    # code 0 si items complets, sinon 2 (pour signaler à l'orchestrateur)
    sys.exit(0 if bundle.get("items") and len(bundle["items"]) == 6 else 2)
