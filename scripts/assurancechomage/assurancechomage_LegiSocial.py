# scripts/assurancechomage/assurancechomage_LegiSocial.py

import json
import re
import requests
from bs4 import BeautifulSoup
from typing import Optional

URL_LEGISOCIAL = "https://www.legisocial.fr/reperes-sociaux/taux-cotisations-sociales-urssaf-2025.html"

def _txt(el) -> str:
    return el.get_text(" ", strip=True) if el else ""

def _lct(el) -> str:
    return _txt(el).lower()

def parse_taux(text: str) -> Optional[float]:
    """'4,00 %' -> 0.04"""
    if not text:
        return None
    try:
        cleaned = (
            text.replace('\u202f', '')
                .replace('\xa0', '')
                .replace(' ', '')
                .replace(',', '.')
                .replace('%', '')
                .strip()
        )
        return round(float(cleaned) / 100.0, 5)
    except ValueError:
        return None

def make_payload(rate: Optional[float]) -> dict:
    return {
        "id": "assurance_chomage",
        "type": "cotisation",
        "libelle": "Assurance Chômage",
        "base": "brut",
        "valeurs": {"salarial": None, "patronal": rate},
        "meta": {
            "source": [{"url": URL_LEGISOCIAL, "label": "LegiSocial", "date_doc": ""}],
            "generator": "scripts/assurancechomage/assurancechomage_LegiSocial.py",
        },
    }

def scrape_legisocial_assurance_chomage() -> Optional[float]:
    r = requests.get(
        URL_LEGISOCIAL,
        timeout=25,
        headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120 Safari/537.36"}
    )
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "lxml")

    # Parcourt toutes les lignes et cherche EXACTEMENT la structure décrite :
    # td0: "Assurance chômage (A compter du 1er mai 2025)"
    # td1: "Tranche A + B"
    # td4: patronal (ex: "4,00 %")
    for tr in soup.find_all("tr"):
        tds = tr.find_all("td")
        if len(tds) < 5:
            continue

        c0 = _lct(tds[0])
        c1 = _lct(tds[1])

        # tolérances: accents/espaces/variantes du '+'
        if ("assurance chômage" in c0 or "assurance chomage" in c0) and \
           ("compter du" in c0 or "à compter du" in c0 or "(a compter du" in c0):
            # normaliser "tranche a + b"
            norm_c1 = re.sub(r"\s+", "", c1)
            if "tranchea+b" in norm_c1 or "trancheaetb" in norm_c1 or "tranchea+b" in c1:
                patronal_txt = _txt(tds[4])
                rate = parse_taux(patronal_txt)
                if rate is not None:
                    return rate

    # Fallback: si la ligne exacte n'est pas trouvée, tente la première ligne
    # "Assurance chômage" où la 5e cellule contient un pourcentage.
    for tr in soup.find_all("tr"):
        tds = tr.find_all("td")
        if len(tds) < 5:
            continue
        if ("assurance chômage" in _lct(tds[0]) or "assurance chomage" in _lct(tds[0])):
            txt = _txt(tds[4])
            if "%" in txt:
                rate = parse_taux(txt)
                if rate is not None:
                    return rate

    return None

if __name__ == "__main__":
    try:
        rate = scrape_legisocial_assurance_chomage()
        print(json.dumps(make_payload(rate), ensure_ascii=False))
    except Exception:
        print(json.dumps(make_payload(None), ensure_ascii=False))
