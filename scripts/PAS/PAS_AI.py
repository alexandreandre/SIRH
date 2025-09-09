# scripts/PAS/PAS_AI.py

import json
import os
import re
import sys
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from googlesearch import search
from openai import OpenAI

load_dotenv()

# --- Constantes ---
PREFERRED_URL = "https://bofip.impots.gouv.fr/bofip/11255-PGP.html/identifiant%3DBOI-BAREME-000037-20250410"
SEARCH_QUERIES = [
    "BOFiP barème taux neutre prélèvement à la source actuel mensuel",
    "BOI-BAREME-000037 actuel taux par défaut PAS",
    "grille taux par défaut prélèvement à la source actuel bofip"
]

NBSP = "\xa0"
NNBSP = "\u202f"
THIN = "\u2009"

# ---------- Utils ----------
def iso_now() -> str:
    """Retourne la date et l'heure actuelles au format ISO 8601 UTC."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def _to_float(x: Any) -> Optional[float]:
    if x is None: return None
    if isinstance(x, (int, float)): return float(x)
    s = str(x).strip().replace(NBSP, "").replace(NNBSP, "").replace(THIN, "").replace(" ", "").replace(",", ".")
    m = re.search(r"-?\d+(?:\.\d+)?", s)
    return float(m.group(0)) if m else None

def _download(url: str) -> str:
    r = requests.get(url, timeout=30, headers={"User-Agent": "Mozilla/5.0", "Accept-Language": "fr"})
    r.raise_for_status()
    return r.text

def extract_json_with_gpt(page_text: str, prompt: str) -> Optional[Dict[str, Any]]:
    if not os.getenv("OPENAI_API_KEY"):
        print("ERREUR : OPENAI_API_KEY manquant.", file=sys.stderr)
        return None
    try:
        client = OpenAI()
        print("   - Appel GPT-4o-mini pour extraction JSON…", file=sys.stderr)
        resp = client.chat.completions.create(
            model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": "Tu es un extracteur de données réglementaires. Réponds en JSON STRICT et valide."},
                {"role": "user", "content": prompt}
            ],
            temperature=0
        )
        raw = resp.choices[0].message.content.strip()
        print(f"   - Réponse brute : {raw[:220]}{'…' if len(raw)>220 else ''}", file=sys.stderr)
        return json.loads(raw)
    except Exception as e:
        print(f"   - ERREUR OpenAI/JSON : {e}", file=sys.stderr)
        return None

# ---------- Core ----------
def get_pas_baremes_via_ai() -> Optional[Dict[str, List[Dict[str, any]]]]:
    schema = """
Lis un texte officiel décrivant le barème du TAUX NEUTRE du prélèvement à la source.
Extrait UNIQUEMENT le barème MENSUEL pour TROIS zones :
1) Métropole et hors de France  -> clé "metropole"
2) Guadeloupe / Réunion / Martinique -> clé "grm"
3) Guyane / Mayotte -> clé "gm"

Pour chaque zone, renvoie un tableau ordonné de tranches. Chaque objet contient :
- "plafond": la borne SUPÉRIEURE en euros (ex: 1620.0) ; null pour la dernière tranche sans plafond
- "taux": le POURCENTAGE en nombre (ex: 13.8 pour « 13,8 % »)

Réponse STRICTEMENT au format JSON suivant, sans texte additionnel :
{
  "metropole": [ { "plafond": 1620.0, "taux": 0.0 }, ..., { "plafond": null, "taux": 43.0 } ],
  "grm": [ ... ],
  "gm":  [ ... ]
}
""".strip()

    candidates: List[str] = [PREFERRED_URL]

    for q in SEARCH_QUERIES:
        try:
            print(f"Recherche Google : {q}", file=sys.stderr)
            for u in search(q, num_results=5, lang="fr"):
                if u not in candidates: candidates.append(u)
        except Exception as e:
            print(f"   - ERREUR de recherche: {e}", file=sys.stderr)

    for i, url in enumerate(candidates, start=1):
        print(f"\n--- Tentative {i}/{len(candidates)} : {url}", file=sys.stderr)
        try:
            html = _download(url)
            soup = BeautifulSoup(html, "lxml")
            page_text = soup.get_text(" ", strip=True)
            prompt = f"{schema}\n\nTEXTE À ANALYSER:\n---\n{page_text}\n---"
            data = extract_json_with_gpt(page_text, prompt)
            
            if not data:
                print("   - Extraction vide.", file=sys.stderr)
                continue

            # Validation et normalisation
            out: Dict[str, List[Dict[str, any]]] = {}
            key_mapping = {"metropole": "metropole", "grm": "guadeloupe_reunion_martinique", "gm": "guyane_mayotte"}
            
            valid = True
            for src_key, dst_key in key_mapping.items():
                if src_key not in data or not isinstance(data[src_key], list) or not data[src_key]:
                    print(f"   - Clé manquante/incorrecte dans le JSON de l'IA: {src_key}", file=sys.stderr)
                    valid = False
                    break
                
                tranches = []
                for item in data[src_key]:
                    plafond = _to_float(item.get("plafond"))
                    taux_pct = _to_float(item.get("taux"))
                    if taux_pct is None:
                        tranches = [] # Invalide si un taux manque
                        break
                    tranches.append({"plafond": plafond, "taux": round(taux_pct / 100.0, 5)})
                
                if not tranches:
                    valid = False
                    break
                
                tranches.sort(key=lambda x: (float('inf') if x["plafond"] is None else x["plafond"]))
                out[dst_key] = tranches
            
            if valid:
                print(f"✅ Barèmes valides extraits de cette page.", file=sys.stderr)
                return out
            else:
                print("   - Données invalides ou incomplètes, page suivante.", file=sys.stderr)
                
        except Exception as e:
            print(f"   - ERREUR lors du traitement de la page : {e}", file=sys.stderr)

    print("\n❌ Aucun JSON valide n'a pu être obtenu via l'IA.", file=sys.stderr)
    return None

# ---------- Main ----------
def main():
    """Orchestre le scraping IA et génère la sortie JSON pour l'orchestrateur."""
    zones_data = get_pas_baremes_via_ai()

    if zones_data is None:
        print("ERREUR CRITIQUE: Le scraping du PAS via IA a échoué.", file=sys.stderr)
        sys.exit(1)

    payload = {
        "id": "pas_taux_neutre",
        "type": "bareme_imposition",
        "libelle": "Prélèvement à la Source (PAS) - Grille de taux par défaut",
        "sections": zones_data,
        "meta": {
            "source": [{
                "url": f"google_search:?q={SEARCH_QUERIES[0].replace(' ', '+')}",
                "label": "Recherche Google + Extraction AI",
                "date_doc": ""
            }],
            "scraped_at": iso_now(),
            "generator": "scripts/PAS/PAS_AI.py",
            "method": "ai"
        }
    }

    print(json.dumps(payload, ensure_ascii=False))


if __name__ == "__main__":
    main()