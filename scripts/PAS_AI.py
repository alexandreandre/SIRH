# scripts/PAS_AI.py

import json
import os
import re
import requests
from bs4 import BeautifulSoup
from googlesearch import search
from dotenv import load_dotenv
from openai import OpenAI
from pathlib import Path
from typing import Any, Dict, List, Optional

load_dotenv()

FICHIER_TAUX = 'config/taux_cotisations.json'
# Cible principale + requêtes de recherche
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
def _to_float(x: Any) -> Optional[float]:
    if x is None:
        return None
    if isinstance(x, (int, float)):
        return float(x)
    s = str(x).strip().replace(NBSP, "").replace(NNBSP, "").replace(THIN, "").replace(" ", "")
    s = s.replace(",", ".")
    m = re.search(r"-?\d+(?:\.\d+)?", s)
    return float(m.group(0)) if m else None

def _download(url: str) -> str:
    r = requests.get(url, timeout=30, headers={"User-Agent": "Mozilla/5.0", "Accept-Language": "fr"})
    r.raise_for_status()
    return r.text

def extract_json_with_gpt(page_text: str, prompt: str) -> Optional[Dict[str, Any]]:
    if not os.getenv("OPENAI_API_KEY"):
        print("ERREUR : OPENAI_API_KEY manquant.")
        return None
    try:
        client = OpenAI()
        print("   - Appel GPT-4o-mini pour extraction JSON…")
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
        print(f"   - Réponse brute : {raw[:220]}{'…' if len(raw)>220 else ''}")
        return json.loads(raw)
    except Exception as e:
        print(f"   - ERREUR OpenAI/JSON : {e}")
        return None

# ---------- Core ----------
def get_pas_baremes_via_ai() -> Optional[Dict[str, List[Dict[str, float]]]]:
    schema = """
Lis un texte officiel décrivant le barème du TAUX NEUTRE du prélèvement à la source applicable à compter du 1er mai 2025.
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

    # Recherche Google
    for q in SEARCH_QUERIES:
        try:
            print(f"Recherche : {q}")
            for u in search(q, num_results=15, lang="fr"):
                if u not in candidates:
                    candidates.append(u)
        except Exception as e:
            print(f"   - ERREUR recherche: {e}")

    # Parcours des pages
    for i, url in enumerate(candidates, start=1):
        print(f"\n--- Tentative {i}/{len(candidates)} : {url}")
        try:
            html = _download(url)
            soup = BeautifulSoup(html, "lxml")
            page_text = soup.get_text(" ", strip=True)
            prompt = f"{schema}\n\nTEXTE À ANALYSER:\n---\n{page_text}\n---"
            data = extract_json_with_gpt(page_text, prompt)
            if not data:
                print("   - Extraction vide.")
                continue

            # Validation minimale
            for key in ("metropole", "grm", "gm"):
                if key not in data or not isinstance(data[key], list) or not data[key]:
                    print(f"   - Clé manquante/incorrecte: {key}")
                    data = None
                    break
            if not data:
                continue

            # Conversion en taux réels et tri
            out: Dict[str, List[Dict[str, float]]] = {}
            mapping = [("metropole", "metropole"),
                       ("grm", "guadeloupe_reunion_martinique"),
                       ("gm", "guyane_mayotte")]
            for src, dst in mapping:
                conv: List[Dict[str, float]] = []
                for item in data[src]:
                    plafond = _to_float(item.get("plafond", None))
                    taux_pct = _to_float(item.get("taux", None))
                    if taux_pct is None:
                        conv = []
                        break
                    conv.append({"plafond": plafond, "taux": round(taux_pct / 100.0, 5)})
                if not conv:
                    out = {}
                    break
                conv.sort(key=lambda x: (float('inf') if x["plafond"] is None else x["plafond"]))
                out[dst] = conv

            if out and all(k in out for k in ("metropole", "guadeloupe_reunion_martinique", "guyane_mayotte")):
                print(
                    f"✅ Barèmes AI: "
                    f"{len(out['metropole'])} métropole, "
                    f"{len(out['guadeloupe_reunion_martinique'])} GRM, "
                    f"{len(out['guyane_mayotte'])} GM."
                )
                return out
            else:
                print("   - JSON incomplet, page suivante.")
        except Exception as e:
            print(f"   - ERREUR page: {e}")

    print("\n❌ Aucun JSON valide obtenu via IA.")
    return None

def update_config_with_pas(zones: Dict[str, List[Dict[str, float]]], fichier: str = FICHIER_TAUX) -> None:
    path = Path(fichier)
    if not path.exists():
        raise FileNotFoundError(f"Fichier introuvable: {fichier}")

    with path.open("r", encoding="utf-8") as f:
        config = json.load(f)

    tc = config.setdefault("TAUX_COTISATIONS", {})

    tc["pas_bareme_taux_neutre_2025"] = {
        "libelle": "Barème taux neutre PAS 2025 (mensuel, métropole)",
        "base": "net_imposable_mensuel",
        "tranches": zones["metropole"],
    }
    tc["pas_bareme_taux_neutre_2025_outremer_grm"] = {
        "libelle": "Barème taux neutre PAS 2025 (Guadeloupe, Réunion, Martinique)",
        "base": "net_imposable_mensuel",
        "tranches": zones["guadeloupe_reunion_martinique"],
    }
    tc["pas_bareme_taux_neutre_2025_outremer_gm"] = {
        "libelle": "Barème taux neutre PAS 2025 (Guyane, Mayotte)",
        "base": "net_imposable_mensuel",
        "tranches": zones["guyane_mayotte"],
    }

    with path.open("w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)
    print("✅ JSON mis à jour avec les 3 zones PAS 2025 (via IA).")

# ---------- Main ----------
if __name__ == "__main__":
    try:
        zones = get_pas_baremes_via_ai()
        if zones:
            update_config_with_pas(zones)
        else:
            print("Arrêt: extraction IA impossible.")
    except Exception as e:
        print(f"ERREUR: {e}")
