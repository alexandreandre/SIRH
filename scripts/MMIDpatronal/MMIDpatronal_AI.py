# scripts/MMIDpatronal/MMIDpatronal_AI.py
import json
import os
from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from googlesearch import search
from openai import OpenAI

load_dotenv()

SEARCH_QUERY = "taux cotisation assurance maladie urssaf actuel taux plein taux réduit "

def iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def _fetch_text(url: str) -> str | None:
    try:
        r = requests.get(url, timeout=25, headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        return soup.get_text(" ", strip=True)
    except Exception:
        return None

def _pct_to_rate(val) -> float | None:
    try:
        return round(float(val) / 100.0, 6)
    except Exception:
        return None

def _extract_two_rates_with_gpt(page_text: str) -> dict[str, float | None]:
    """
    Extrait DEUX pourcentages:
      {"plein_percent": <number|null>, "reduit_percent": <number|null>}
    Retourne en taux décimaux:
      {"patronal_plein": <float|None>, "patronal_reduit": <float|None>}
    """
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return {"patronal_plein": None, "patronal_reduit": None}

    client = OpenAI(api_key=api_key)
    prompt = (
        "À partir du texte, extrait UNIQUEMENT les pourcentages de la cotisation patronale « Assurance maladie » (France, 2025):\n"
        "- plein_percent : taux plein (droit commun)\n"
        "- reduit_percent : taux réduit (rémunération sous le seuil réglementaire ~3,5 SMIC)\n\n"
        'Réponds UNIQUEMENT en JSON valide exactement: {"plein_percent": <number|null>, "reduit_percent": <number|null>} '
        "avec nombres décimaux (point) sans symbole %; mets null si absent.\n\n"
        "Texte:\n---\n" + page_text[:15000] + "\n---"
    )
    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            response_format={"type": "json_object"},
            temperature=0,
            messages=[
                {"role": "system", "content": "Assistant d'extraction. Ne renvoie que du JSON valide."},
                {"role": "user", "content": prompt},
            ],
        )
        data = json.loads(resp.choices[0].message.content.strip())
        return {
            "patronal_plein": _pct_to_rate(data.get("plein_percent")),
            "patronal_reduit": _pct_to_rate(data.get("reduit_percent")),
        }
    except Exception:
        return {"patronal_plein": None, "patronal_reduit": None}

def build_payload(rate_plein: float | None, rate_reduit: float | None, sources: list[str]) -> dict:
    return {
        "id": "securite_sociale_maladie",
        "type": "cotisation",
        "libelle": "Sécurité sociale - Maladie, Maternité, Invalidité, Décès",
        "base": "brut",
        "valeurs": {
            "salarial": None,
            "patronal_plein": rate_plein,
            "patronal_reduit": rate_reduit,
        },
        "meta": {
            "source": [{"url": u, "label": "Web + IA", "date_doc": ""} for u in sources],
            "scraped_at": iso_now(),
            "generator": "scripts/MMIDpatronal/MMIDpatronal_AI.py",
            "method": "ai",
        },
    }

def main() -> None:
    # Agrégation multi-pages jusqu’à obtenir les DEUX taux.
    rates = {"patronal_plein": None, "patronal_reduit": None}
    src_set: set[str] = set()

    try:
        results = list(search(SEARCH_QUERY, num_results=50, lang="fr"))
    except Exception:
        results = []

    for url in results:
        txt = _fetch_text(url)
        if not txt:
            continue
        cand = _extract_two_rates_with_gpt(txt)
        updated = False
        if rates["patronal_plein"] is None and cand.get("patronal_plein") is not None:
            rates["patronal_plein"] = cand["patronal_plein"]
            updated = True
        if rates["patronal_reduit"] is None and cand.get("patronal_reduit") is not None:
            rates["patronal_reduit"] = cand["patronal_reduit"]
            updated = True
        if updated:
            src_set.add(url)
        if rates["patronal_plein"] is not None and rates["patronal_reduit"] is not None:
            break

    # Construit la sortie JSON stricte.
    payload = build_payload(rates["patronal_plein"], rates["patronal_reduit"], list(src_set))
    print(json.dumps(payload, ensure_ascii=False))

if __name__ == "__main__":
    main()
