# scripts/CSA/CSA_AI.py

import json
import os
import sys
from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup
from googlesearch import search
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

SEARCH_QUERY = "taux Contribution solidarité autonomie CSA employeur actuel"
RAW_OUT = "staging/cotisations.csa.raw.json"


def iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def fetch_text(url: str) -> str | None:
    try:
        r = requests.get(url, timeout=25, headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        return soup.get_text(" ", strip=True)
    except Exception as e:
        print(f"ERR fetch {url}: {e}", file=sys.stderr)
        return None


def extract_percent_with_gpt(page_text: str) -> float | None:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("ERR: OPENAI_API_KEY absente.", file=sys.stderr)
        return None
    try:
        client = OpenAI(api_key=api_key)
        prompt = (
            "Tu lis un texte en français. Trouve le taux patronal de la "
            '"Contribution Solidarité Autonomie (CSA)" appliqué aux employeurs. '
            "Réponds UNIQUEMENT en JSON valide, au format:\n"
            '{"csa_percent": 0.30}\n'
            "- Nombre décimal avec point.\n"
            "- Si absent, réponds {\"csa_percent\": null}.\n\n"
            "Texte à analyser:\n---\n" + page_text[:15000] + "\n---"
        )
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": "Assistant d'extraction de données, sortie JSON stricte."},
                {"role": "user", "content": prompt},
            ],
            temperature=0,
        )
        raw = resp.choices[0].message.content.strip()
        data = json.loads(raw)
        val = data.get("csa_percent", None)
        if val is None:
            return None
        # convert pourcentage -> taux
        return round(float(val) / 100.0, 6)
    except Exception as e:
        print(f"ERR OpenAI: {e}", file=sys.stderr)
        return None


def build_payload(rate_patronal: float, source_url: str) -> dict:
    return {
        "id": "csa",
        "type": "cotisation",
        "libelle": "Contribution Solidarité Autonomie (CSA)",
        "base": "brut",
        "valeurs": {"salarial": None, "patronal": rate_patronal},
        "meta": {
            "source": [{"url": source_url, "label": "", "date_doc": ""}],
            "scraped_at": iso_now(),
            "generator": "CSA_AI.py",
            "method": "ai",
        },
    }


def write_raw(payload: dict) -> None:
    os.makedirs(os.path.dirname(RAW_OUT), exist_ok=True)
    with open(RAW_OUT, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def main() -> None:
    results = list(search(SEARCH_QUERY, num_results=10, lang="fr"))
    for url in results:
        txt = fetch_text(url)
        if not txt:
            continue
        rate = extract_percent_with_gpt(txt)
        if rate is None:
            continue
        payload = build_payload(rate, url)
        write_raw(payload)
        print(json.dumps(payload, ensure_ascii=False))
        return
    print("ERREUR: aucune valeur CSA extraite par IA.", file=sys.stderr)
    sys.exit(2)


if __name__ == "__main__":
    main()
