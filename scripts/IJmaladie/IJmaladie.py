# scripts/IJmaladie/IJmaladie.py
import json
import re
from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup

URL_AMELI = "https://www.ameli.fr/entreprise/vos-salaries/montants-reference/indemnites-journalieres-montants-maximum"

def iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def _to_float_eur(text: str) -> float | None:
    if not text:
        return None
    # garde le premier nombre décimal, traite espaces insécables et virgules
    cleaned = text.replace("\xa0", " ").replace("\u202f", " ").replace("€", "").strip()
    m = re.search(r"(\d+(?:[.,]\d+)?)", cleaned)
    if not m:
        return None
    try:
        return round(float(m.group(1).replace(",", ".")), 2)
    except Exception:
        return None

def _fetch_page(url: str) -> BeautifulSoup:
    r = requests.get(
        url,
        timeout=25,
        headers={
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "fr-FR,fr;q=0.9",
        },
    )
    r.raise_for_status()
    return BeautifulSoup(r.text, "html.parser")

def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s.lower().strip()) if s else ""

def scrape_ij_plafonds() -> dict[str, float | None]:
    """
    Extrait les montants maximums journaliers (en euros) :
      - maladie
      - maternité_paternite
      - at_mp
      - at_mp_majoree  (à compter du 29e jour)
    """
    soup = _fetch_page(URL_AMELI)
    vals = {"maladie": None, "maternite_paternite": None, "at_mp": None, "at_mp_majoree": None}

    # Parcours de tous les tableaux et lignes
    for table in soup.find_all("table"):
        for tr in table.find_all("tr"):
            cells = tr.find_all(["th", "td"])
            if len(cells) < 2:
                continue
            label = _norm(cells[0].get_text(" ", strip=True))
            value_text = cells[-1].get_text(" ", strip=True)
            val = _to_float_eur(value_text)
            if val is None:
                continue

            # Règles de mapping robustes
            if ("maternité" in label) or ("paternité" in label) or ("adoption" in label):
                vals["maternite_paternite"] = val
            elif ("accident du travail" in label) or ("maladie professionnelle" in label) or ("at/mp" in label) or ("at mp" in label):
                if ("29" in label) or ("à compter du 29" in label) or ("maj" in label):
                    vals["at_mp_majoree"] = val
                else:
                    vals["at_mp"] = val
            elif ("arrêt maladie" in label) or (("maladie" in label) and ("accident" not in label) and ("professionnelle" not in label)):
                vals["maladie"] = val

    return vals

def build_payload(vals: dict[str, float | None]) -> dict:
    return {
        "id": "ij_maladie",
        "type": "secu",
        "libelle": "Indemnités journalières — montants maximums",
        "base": None,
        "valeurs": {
            "maladie": vals.get("maladie"),
            "maternite_paternite": vals.get("maternite_paternite"),
            "at_mp": vals.get("at_mp"),
            "at_mp_majoree": vals.get("at_mp_majoree"),
            "unite": "EUR/jour",
        },
        "meta": {
            "source": [{"url": URL_AMELI, "label": "ameli.fr — IJ montants maximum", "date_doc": ""}],
            "scraped_at": iso_now(),
            "generator": "scripts/IJmaladie/IJmaladie.py",
            "method": "primary",
        },
    }

def main() -> None:
    vals = scrape_ij_plafonds()
    payload = build_payload(vals)
    # Sortie JSON stricte, aucun autre print
    print(json.dumps(payload, ensure_ascii=False))

if __name__ == "__main__":
    main()
