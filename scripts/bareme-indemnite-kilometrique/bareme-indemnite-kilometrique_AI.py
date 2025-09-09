# scripts/bareme-indemnite-kilometrique/bareme-indemnite-kilometrique_AI.py

import json
import os
from datetime import datetime, timezone

from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()


def iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def build_prompt() -> str:
    # Demande DIRECTE au modèle. JSON strict. Valeurs en float ou null si incertain.
    return """
Tu dois fournir le barème kilométrique FRANCE 2025 pour VOITURES, MOTOCYCLETTES et CYCLOMOTEURS.
Donne UNIQUEMENT un JSON STRICT, sans texte hors JSON, avec la structure exacte ci-dessous.
Rappels:
- Chaque formule est: coût = a * d + b, où a est en €/km (float) et b en € (float). Si l'information n'est pas certaine, mets null.
- Segments de distance:
  * VOITURES: seg1 d≤5000 ; seg2 5001–20000 ; seg3 >20000
  * MOTOCYCLETTES: seg1 d≤3000 ; seg2 3001–6000 ; seg3 >6000
  * CYCLOMOTEURS: seg1 d≤3000 ; seg2 3001–6000 ; seg3 >6000
- Tranches de puissance:
  * VOITURES (5): (≤3 CV), (4 CV), (5 CV), (6 CV), (≥7 CV)
  * MOTOCYCLETTES (3): (1–2 CV), (3–5 CV), (≥6 CV)
  * CYCLOMOTEURS (1): sans CV
- Toutes les valeurs doivent être des nombres JSON (ex: 0.529, 1065.0) ou null si non certain.
- Ne fournis AUCUNE clé supplémentaire. Ne fournis AUCUNE explication.

Format EXACT à renvoyer:

{
  "voitures": [
    { "cv_min": null, "cv_max": 3, "formules": [
      { "segment": 1, "a": <float_or_null>, "b": <float_or_null> },
      { "segment": 2, "a": <float_or_null>, "b": <float_or_null> },
      { "segment": 3, "a": <float_or_null>, "b": <float_or_null> }
    ]},
    { "cv_min": 4, "cv_max": 4, "formules": [
      { "segment": 1, "a": <float_or_null>, "b": <float_or_null> },
      { "segment": 2, "a": <float_or_null>, "b": <float_or_null> },
      { "segment": 3, "a": <float_or_null>, "b": <float_or_null> }
    ]},
    { "cv_min": 5, "cv_max": 5, "formules": [
      { "segment": 1, "a": <float_or_null>, "b": <float_or_null> },
      { "segment": 2, "a": <float_or_null>, "b": <float_or_null> },
      { "segment": 3, "a": <float_or_null>, "b": <float_or_null> }
    ]},
    { "cv_min": 6, "cv_max": 6, "formules": [
      { "segment": 1, "a": <float_or_null>, "b": <float_or_null> },
      { "segment": 2, "a": <float_or_null>, "b": <float_or_null> },
      { "segment": 3, "a": <float_or_null>, "b": <float_or_null> }
    ]},
    { "cv_min": 7, "cv_max": null, "formules": [
      { "segment": 1, "a": <float_or_null>, "b": <float_or_null> },
      { "segment": 2, "a": <float_or_null>, "b": <float_or_null> },
      { "segment": 3, "a": <float_or_null>, "b": <float_or_null> }
    ]}
  ],
  "motocyclettes": [
    { "cv_min": 1, "cv_max": 2, "formules": [
      { "segment": 1, "a": <float_or_null>, "b": <float_or_null> },
      { "segment": 2, "a": <float_or_null>, "b": <float_or_null> },
      { "segment": 3, "a": <float_or_null>, "b": <float_or_null> }
    ]},
    { "cv_min": 3, "cv_max": 5, "formules": [
      { "segment": 1, "a": <float_or_null>, "b": <float_or_null> },
      { "segment": 2, "a": <float_or_null>, "b": <float_or_null> },
      { "segment": 3, "a": <float_or_null>, "b": <float_or_null> }
    ]},
    { "cv_min": 6, "cv_max": null, "formules": [
      { "segment": 1, "a": <float_or_null>, "b": <float_or_null> },
      { "segment": 2, "a": <float_or_null>, "b": <float_or_null> },
      { "segment": 3, "a": <float_or_null>, "b": <float_or_null> }
    ]}
  ],
  "cyclomoteurs": [
    { "cv_min": null, "cv_max": null, "formules": [
      { "segment": 1, "a": <float_or_null>, "b": <float_or_null> },
      { "segment": 2, "a": <float_or_null>, "b": <float_or_null> },
      { "segment": 3, "a": <float_or_null>, "b": <float_or_null> }
    ]}
  ]
}
""".strip()


def validate_payload(data: dict) -> bool:
    try:
        if not isinstance(data.get("voitures"), list) or len(data["voitures"]) != 5:
            return False
        for tr in data["voitures"]:
            if len(tr.get("formules", [])) != 3:
                return False
            for f in tr["formules"]:
                if not all(k in f for k in ("segment", "a", "b")):
                    return False
        if not isinstance(data.get("motocyclettes"), list) or len(data["motocyclettes"]) != 3:
            return False
        for tr in data["motocyclettes"]:
            if len(tr.get("formules", [])) != 3:
                return False
        if not isinstance(data.get("cyclomoteurs"), list) or len(data["cyclomoteurs"]) != 1:
            return False
        if len(data["cyclomoteurs"][0].get("formules", [])) != 3:
            return False
        return True
    except Exception:
        return False


def get_baremes_via_ai() -> dict | None:
    """Interroge directement l'API pour obtenir le JSON des barèmes, sans navigation web."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return None
    try:
        client = OpenAI(api_key=api_key)
        prompt = build_prompt()
        resp = client.chat.completions.create(
            model="gpt-4.1",
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": "Tu es un extracteur de données. Réponds en JSON STRICT valide uniquement."},
                {"role": "user", "content": prompt},
            ],
            temperature=0,
        )
        data = json.loads(resp.choices[0].message.content.strip())
        if not validate_payload(data):
            return None
        # Arrondis légers si nombres présents
        for bloc in ("voitures", "motocyclettes", "cyclomoteurs"):
            for tr in data[bloc]:
                for f in tr["formules"]:
                    if f["a"] is not None:
                        f["a"] = round(float(f["a"]), 3)
                    if f["b"] is not None:
                        f["b"] = round(float(f["b"]), 3)
        return data
    except Exception:
        return None


def build_payload(ai_data: dict | None) -> dict:
    veh = {
        "voitures": {
            "base": "distance_km",
            "segments": [
                {"d_min": 0, "d_max": 5000},
                {"d_min": 5001, "d_max": 20000},
                {"d_min": 20001, "d_max": None},
            ],
            "tranches_cv": (ai_data or {}).get("voitures") or [],
        },
        "motocyclettes": {
            "base": "distance_km",
            "segments": [
                {"d_min": 0, "d_max": 3000},
                {"d_min": 3001, "d_max": 6000},
                {"d_min": 6001, "d_max": None},
            ],
            "tranches_cv": (ai_data or {}).get("motocyclettes") or [],
        },
        "cyclomoteurs": {
            "base": "distance_km",
            "segments": [
                {"d_min": 0, "d_max": 3000},
                {"d_min": 3001, "d_max": 6000},
                {"d_min": 6001, "d_max": None},
            ],
            "tranches_cv": (ai_data or {}).get("cyclomoteurs") or [],
        },
    }
    return {
        "id": "baremes_km",
        "type": "barème_kilométrique",
        "libelle": "Barème kilométrique 2025 (IA directe)",
        "annee": 2025,
        "vehicules": veh,
        "meta": {
            "source": [{"url": "", "label": "OpenAI (réponse modèle, sans navigation)", "date_doc": ""}],
            "scraped_at": iso_now(),
            "generator": "scripts/bareme-indemnite-kilometrique/bareme-indemnite-kilometrique_AI.py",
            "method": "ai",
        },
    }


if __name__ == "__main__":
    data = get_baremes_via_ai()
    payload = build_payload(data)
    print(json.dumps(payload, ensure_ascii=False))
