# scripts/bareme-indemnite-kilometrique_AI.py

import json
import os
import requests
from bs4 import BeautifulSoup
from openai import OpenAI
from googlesearch import search
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

FICHIER_TAUX = "config/taux_cotisations.json"

SEARCH_QUERIES = [
    # Sources usuelles
    "site:service-public.fr barème kilométrique actuel voitures motocyclettes cyclomoteurs",
    "site:legisocial.fr barème kilométrique actuel voitures motocyclettes cyclomoteurs",
    "barème kilométrique actuel indemnités kilométriques voitures motos cyclomoteurs"
]

def extract_json_with_gpt(page_text: str, prompt: str) -> dict | None:
    if not os.getenv("OPENAI_API_KEY"):
        print("ERREUR : OPENAI_API_KEY manquante.")
        return None
    try:
        client = OpenAI()
        print("   - Appel modèle gpt-4o-mini (JSON forcé)...")
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": "Tu es un extracteur de données. Réponds en JSON STRICT valide uniquement."},
                {"role": "user", "content": prompt + "\n\n---\n" + page_text}
            ],
            temperature=0
        )
        txt = resp.choices[0].message.content.strip()
        return json.loads(txt)
    except Exception as e:
        print(f"   - ERREUR API/JSON : {e}")
        return None

def build_prompt() -> str:
    # Extrait EXACTEMENT la structure attendue par le code classique (mêmes clés/segments)
    return """
Tu reçois le texte brut d’une page web décrivant les barèmes kilométriques 2025.
Objectif : extraire les coefficients et constantes des formules pour VOITURES, MOTOCYCLETTES, CYCLOMOTEURS.

Règles d’extraction (obligatoires) :
- Détecte pour chaque catégorie les 3 segments de distance :
  * VOITURES : segment 1 = d ≤ 5 000 km ; segment 2 = 5 001–20 000 km ; segment 3 = > 20 000 km
  * MOTOCYCLETTES : segment 1 = d ≤ 3 000 km ; segment 2 = 3 001–6 000 km ; segment 3 = > 6 000 km
  * CYCLOMOTEURS : segment 1 = d ≤ 3 000 km ; segment 2 = 3 001–6 000 km ; segment 3 = > 6 000 km
- Chaque formule est du type : coût = a * d + b
  * 'a' est en €/km (ex “d x 0,529” → a=0.529)
  * 'b' est la constante en € (ex “+ 1 065” → b=1065.0). Si absente, b=0.0
- Gère virgule/point décimal et séparateurs d’espace/milliers.
- Convertis toutes les valeurs en nombres décimaux (float).
- Pour VOITURES, produis 5 tranches en fonction de la puissance administrative :
  1) 3 CV et moins → {"cv_min": null, "cv_max": 3}
  2) 4 CV → {"cv_min": 4, "cv_max": 4}
  3) 5 CV → {"cv_min": 5, "cv_max": 5}
  4) 6 CV → {"cv_min": 6, "cv_max": 6}
  5) 7 CV et plus → {"cv_min": 7, "cv_max": null}
- Pour MOTOCYCLETTES, produis 3 tranches :
  1) 1 ou 2 CV → {"cv_min": 1, "cv_max": 2}
  2) 3, 4 ou 5 CV → {"cv_min": 3, "cv_max": 5}
  3) plus de 5 CV → {"cv_min": 6, "cv_max": null}
- Pour CYCLOMOTEURS, une seule “tranche” sans CV :
  [{"cv_min": null, "cv_max": null, ...}]

Réponds dans ce JSON EXACT (aucune autre clé, aucun texte hors JSON) :
{
  "voitures": [
    { "cv_min": null, "cv_max": 3, "formules": [
      { "segment": 1, "a": <float>, "b": <float> },
      { "segment": 2, "a": <float>, "b": <float> },
      { "segment": 3, "a": <float>, "b": <float> }
    ]},
    { "cv_min": 4, "cv_max": 4, "formules": [
      { "segment": 1, "a": <float>, "b": <float> },
      { "segment": 2, "a": <float>, "b": <float> },
      { "segment": 3, "a": <float>, "b": <float> }
    ]},
    { "cv_min": 5, "cv_max": 5, "formules": [
      { "segment": 1, "a": <float>, "b": <float> },
      { "segment": 2, "a": <float>, "b": <float> },
      { "segment": 3, "a": <float>, "b": <float> }
    ]},
    { "cv_min": 6, "cv_max": 6, "formules": [
      { "segment": 1, "a": <float>, "b": <float> },
      { "segment": 2, "a": <float>, "b": <float> },
      { "segment": 3, "a": <float>, "b": <float> }
    ]},
    { "cv_min": 7, "cv_max": null, "formules": [
      { "segment": 1, "a": <float>, "b": <float> },
      { "segment": 2, "a": <float>, "b": <float> },
      { "segment": 3, "a": <float>, "b": <float> }
    ]}
  ],
  "motocyclettes": [
    { "cv_min": 1, "cv_max": 2, "formules": [
      { "segment": 1, "a": <float>, "b": <float> },
      { "segment": 2, "a": <float>, "b": <float> },
      { "segment": 3, "a": <float>, "b": <float> }
    ]},
    { "cv_min": 3, "cv_max": 5, "formules": [
      { "segment": 1, "a": <float>, "b": <float> },
      { "segment": 2, "a": <float>, "b": <float> },
      { "segment": 3, "a": <float>, "b": <float> }
    ]},
    { "cv_min": 6, "cv_max": null, "formules": [
      { "segment": 1, "a": <float>, "b": <float> },
      { "segment": 2, "a": <float>, "b": <float> },
      { "segment": 3, "a": <float>, "b": <float> }
    ]}
  ],
  "cyclomoteurs": [
    { "cv_min": null, "cv_max": null, "formules": [
      { "segment": 1, "a": <float>, "b": <float> },
      { "segment": 2, "a": <float>, "b": <float> },
      { "segment": 3, "a": <float>, "b": <float> }
    ]}
  ]
}
"""

def validate_payload(data: dict) -> bool:
    try:
        # Voitures: 5 tranches, chacune 3 segments
        if not isinstance(data.get("voitures"), list) or len(data["voitures"]) != 5:
            return False
        for tr in data["voitures"]:
            if len(tr.get("formules", [])) != 3:
                return False
            for f in tr["formules"]:
                if not all(k in f for k in ("segment", "a", "b")):
                    return False
                if not isinstance(f["a"], (int, float)):
                    return False
        # Moto: 3 tranches
        if not isinstance(data.get("motocyclettes"), list) or len(data["motocyclettes"]) != 3:
            return False
        for tr in data["motocyclettes"]:
            if len(tr.get("formules", [])) != 3:
                return False
        # Cyclo: 1 tranche
        if not isinstance(data.get("cyclomoteurs"), list) or len(data["cyclomoteurs"]) != 1:
            return False
        if len(data["cyclomoteurs"][0].get("formules", [])) != 3:
            return False
        return True
    except Exception:
        return False

def get_baremes_via_ai() -> dict | None:
    prompt = build_prompt()
    results = []
    for q in SEARCH_QUERIES:
        try:
            print(f"Recherche Google: {q}")
            results += list(search(q, num_results=20, lang="fr"))
        except Exception as e:
            print(f"  - ERREUR recherche: {e}")
    # dédoublonnage simple
    seen = set()
    urls = []
    for u in results:
        if u not in seen:
            seen.add(u)
            urls.append(u)
    if not urls:
        print("ERREUR : aucun résultat de recherche.")
        return None

    for i, url in enumerate(urls, 1):
        print(f"\n--- Page {i}/{len(urls)} : {url}")
        try:
            r = requests.get(url, timeout=25, headers={"User-Agent": "Mozilla/5.0"})
            r.raise_for_status()
            soup = BeautifulSoup(r.text, "html.parser")
            page_text = soup.get_text(" ", strip=True)
            data = extract_json_with_gpt(page_text, prompt)
            if data and validate_payload(data):
                print("✅ Extraction IA valide.")
                # arrondis légers
                for bloc in ("voitures", "motocyclettes", "cyclomoteurs"):
                    for tr in data[bloc]:
                        for f in tr["formules"]:
                            f["a"] = round(float(f["a"]), 3)
                            f["b"] = round(float(f["b"]), 3)
                return data
            else:
                print("   - JSON incomplet/invalidé, suite.")
        except Exception as e:
            print(f"   - ERREUR page : {e}")
    print("\n❌ Aucune donnée exploitable.")
    return None

def update_config_file(payload: dict) -> None:
    """
    Met à jour STRICTEMENT les mêmes variables que le code classique :
    - TAUX_COTISATIONS.bareme_kilometrique_voitures_2025.tranches_cv
    - TAUX_COTISATIONS.bareme_kilometrique_motocyclettes_2025.tranches_cv
    - TAUX_COTISATIONS.bareme_kilometrique_cyclomoteurs_2025.tranches_cv
    """
    path = Path(FICHIER_TAUX)
    if not path.exists():
        raise FileNotFoundError(f"Fichier introuvable: {FICHIER_TAUX}")
    cfg = json.loads(path.read_text(encoding="utf-8"))

    tc = cfg.get("TAUX_COTISATIONS")
    if not isinstance(tc, dict):
        raise ValueError("Clé TAUX_COTISATIONS manquante.")
    keys = [
        "bareme_kilometrique_voitures_2025",
        "bareme_kilometrique_motocyclettes_2025",
        "bareme_kilometrique_cyclomoteurs_2025",
    ]
    for k in keys:
        if k not in tc:
            raise KeyError(f"Clé manquante dans le JSON : {k}")

    tc["bareme_kilometrique_voitures_2025"]["tranches_cv"] = payload["voitures"]
    tc["bareme_kilometrique_motocyclettes_2025"]["tranches_cv"] = payload["motocyclettes"]
    tc["bareme_kilometrique_cyclomoteurs_2025"]["tranches_cv"] = payload["cyclomoteurs"]

    path.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")
    print("✅ JSON mis à jour (IA) : voitures, motocyclettes, cyclomoteurs")

if __name__ == "__main__":
    data = get_baremes_via_ai()
    if data:
        update_config_file(data)
