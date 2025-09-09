# scripts/CSA/CSA_LegiSocial.py

import json
import os
import re
import sys
import unicodedata
from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup

URL_LEGISOCIAL = "https://www.legisocial.fr/reperes-sociaux/taux-cotisations-sociales-urssaf-2025.html"
RAW_OUT = "staging/cotisations.csa.raw.json"


# ---------- Utils ----------
def iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def norm(txt: str) -> str:
    if not txt:
        return ""
    txt = txt.strip().lower()
    txt = unicodedata.normalize("NFD", txt)
    return "".join(ch for ch in txt if unicodedata.category(ch) != "Mn")


def parse_percent(txt: str) -> float | None:
    if not txt:
        return None
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*%", txt)
    if not m:
        return None
    val = float(m.group(1).replace(",", "."))
    return round(val / 100.0, 6)  # renvoie le taux (ex: 0.003 pour 0,3%)


# ---------- Scrape ----------
def fetch_page() -> BeautifulSoup:
    r = requests.get(
        URL_LEGISOCIAL,
        timeout=25,
        headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"},
    )
    r.raise_for_status()
    return BeautifulSoup(r.text, "html.parser")


def find_csa_rate(soup: BeautifulSoup) -> float | None:
    # Clés possibles pour identifier la ligne CSA
    keys = (
        "contribution solidarite autonomie",
        "contribution de solidarite pour l'autonomie",
        "contribution de solidarite pour l autonomie",
        "csa",
    )

    # 1) Chercher dans les tableaux
    for table in soup.find_all("table"):
        for tr in table.find_all("tr"):
            cells = tr.find_all(["th", "td"])
            if not cells:
                continue
            label = norm(cells[0].get_text(" ", strip=True))
            if any(k in label for k in keys):
                # collecter tous les pourcentages dans les autres cellules
                rates = []
                for cell in cells[1:]:
                    rate = parse_percent(cell.get_text(" ", strip=True))
                    if rate is not None:
                        rates.append(rate)
                if rates:
                    # CSA est patronale. S'il y a plusieurs % on prend le plus grand non-nul.
                    non_zero = [x for x in rates if x > 0]
                    return (max(non_zero) if non_zero else max(rates))

    # 2) Fallback : chercher un bloc texte proche du mot-clé et un %
    for tag in soup.find_all(text=True):
        t = norm(str(tag))
        if any(k in t for k in keys):
            parent_txt = norm(tag.parent.get_text(" ", strip=True))
            rate = parse_percent(parent_txt)
            if rate is not None:
                return rate

    return None


# ---------- Payload I/O ----------
def build_payload(rate_patronal: float) -> dict:
    return {
        "id": "csa",
        "type": "cotisation",
        "libelle": "Contribution Solidarité Autonomie (CSA)",
        "base": "brut",
        "valeurs": {"salarial": None, "patronal": rate_patronal},
        "meta": {
            "source": [{"url": URL_LEGISOCIAL, "label": "LégiSocial — Taux cotisations sociales URSSAF 2025", "date_doc": ""}],
            "scraped_at": iso_now(),
            "generator": "CSA_LegiSocial.py",
            "method": "secondary",
        },
    }


def write_raw(payload: dict) -> None:
    os.makedirs(os.path.dirname(RAW_OUT), exist_ok=True)
    with open(RAW_OUT, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


# ---------- Main ----------
def main() -> None:
    try:
        soup = fetch_page()
        rate = find_csa_rate(soup)
        if rate is None:
            print("ERREUR: taux CSA introuvable sur Légisocial.", file=sys.stderr)
            sys.exit(2)
        payload = build_payload(rate)
        write_raw(payload)
        print(json.dumps(payload, ensure_ascii=False))
    except Exception as e:
        print(f"ERREUR: {e}", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
