# scripts/CSG/CSG_LegiSocial.py

import json
import re
from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup

URL_LEGISOCIAL = "https://www.legisocial.fr/reperes-sociaux/taux-cotisations-sociales-urssaf-2025.html"


def iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_taux(text: str) -> float | None:
    if not text:
        return None
    m = re.search(r"([0-9]+(?:[.,][0-9]+)?)\s*%", text)
    if not m:
        return None
    try:
        return round(float(m.group(1).replace(",", ".")) / 100.0, 6)
    except Exception:
        return None


def fetch_page() -> BeautifulSoup:
    r = requests.get(
        URL_LEGISOCIAL,
        timeout=25,
        headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"},
    )
    r.raise_for_status()
    return BeautifulSoup(r.text, "html.parser")


def get_taux_csg_legisocial() -> dict | None:
    """
    Retourne {"deductible": float, "non_deductible": float} ou None.
    deductible = CSG déductible
    non_deductible = CSG non déductible + CRDS non déductible
    """
    soup = fetch_page()

    # Trouver le bloc "COTISATIONS CSG et CRDS"
    target_h3 = None
    for h3 in soup.find_all("h3"):
        if "csg" in h3.get_text(strip=True).lower() and "crds" in h3.get_text(strip=True).lower():
            target_h3 = h3
            break
    if not target_h3:
        return None

    table = target_h3.find_next("table")
    if not table:
        return None

    # Parcours du tbody, gestion implicite du rowspan via colonnes présentes
    tbody = table.find("tbody")
    if not tbody:
        return None

    vals = {"deductible": None, "non_deductible_csg": None, "non_deductible_crds": None}
    for tr in tbody.find_all("tr"):
        tds = tr.find_all("td")
        if not tds:
            continue

        # libellé en col 0
        label = tds[0].get_text(" ", strip=True)

        # colonne "Salarié" dépend de la première ligne à 5 colonnes (rowspan) puis 4
        salarie_idx = 3 if len(tds) >= 5 else 2
        if len(tds) <= salarie_idx:
            continue
        val_txt = tds[salarie_idx].get_text(" ", strip=True)
        rate = parse_taux(val_txt)
        if rate is None:
            continue

        l = label.lower()
        if "csg déductible" in l or "csg deductible" in l:
            vals["deductible"] = rate
        elif "csg non déductible" in l or "csg non deductible" in l:
            vals["non_deductible_csg"] = rate
        elif "crds non déductible" in l or "crds non deductible" in l:
            vals["non_deductible_crds"] = rate

        if all(v is not None for v in vals.values()):
            break

    if any(v is None for v in vals.values()):
        return None

    non_deductible = round(vals["non_deductible_csg"] + vals["non_deductible_crds"], 6)
    return {"deductible": vals["deductible"], "non_deductible": non_deductible}


def build_payload(taux: dict | None) -> dict:
    vals = {"salarial": None, "patronal": None}
    if taux is not None:
        vals["salarial"] = {"deductible": taux.get("deductible"), "non_deductible": taux.get("non_deductible")}
    return {
        "id": "csg",
        "type": "cotisation",
        "libelle": "CSG/CRDS",
        "base": "brut",
        "valeurs": vals,
        "meta": {
            "source": [{"url": URL_LEGISOCIAL, "label": "LégiSocial — Taux cotisations URSSAF 2025", "date_doc": ""}],
            "scraped_at": iso_now(),
            "generator": "scripts/CSG/CSG_LegiSocial.py",
            "method": "secondary",
        },
    }


if __name__ == "__main__":
    taux = get_taux_csg_legisocial()
    payload = build_payload(taux)
    print(json.dumps(payload, ensure_ascii=False))
