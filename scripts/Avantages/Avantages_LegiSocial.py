# scripts/Avantages/Avantages_LegiSocial.py

import json
import re
import sys
import requests
from bs4 import BeautifulSoup
from typing import Optional, Dict, List

URL_REPAS = "https://www.legisocial.fr/reperes-sociaux/avantage-en-nature-repas-2025.html"
URL_LOGEMENT = "https://www.legisocial.fr/reperes-sociaux/avantage-en-nature-logement-2025.html"
UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

# ---------- helpers ----------
def _txt(el) -> str:
    return el.get_text(" ", strip=True) if el else ""

def parse_number(text: str) -> Optional[float]:
    if not text:
        return None
    cleaned = (
        text.replace("\u202f", "")
            .replace("\xa0", "")
            .replace("€", "")
            .replace(" ", "")
            .replace(".", "")      # retire séparateurs de milliers type 1.234,56
            .replace(",", ".")
            .strip()
    )
    m = re.search(r"(-?\d+(?:\.\d+)?)", cleaned)
    try:
        return float(m.group(1)) if m else None
    except Exception:
        return None

def make_payload(repas: Optional[float],
                 titre_restaurant: Optional[float],
                 logement_bareme: List[Dict]) -> dict:
    return {
        "id": "avantages_en_nature",
        "type": "param_bundle",
        "items": [
            {"key": "repas_valeur_forfaitaire_eur", "value": repas},
            {"key": "titre_restaurant_exoneration_max_eur", "value": titre_restaurant},
            {"key": "logement_bareme_forfaitaire", "value": logement_bareme},
        ],
        "meta": {
            "source": [
                {"url": URL_REPAS, "label": "LegiSocial (Repas)", "date_doc": ""},
                {"url": URL_LOGEMENT, "label": "LegiSocial (Logement)", "date_doc": ""},
            ],
            "generator": "scripts/Avantages/Avantages_LegiSocial.py",
        },
    }

# ---------- scrapers ----------
def scrape_repas() -> Dict[str, Optional[float]]:
    r = requests.get(URL_REPAS, timeout=25, headers={"User-Agent": UA})
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "lxml")

    repas_val = None
    titre_exo = None

    table = soup.find("table")
    if not table:
        return {"repas": None, "titre": None}

    for tr in table.find_all("tr"):
        tds = tr.find_all("td")
        if len(tds) != 2:
            continue
        lib = _txt(tds[0]).lower()
        val = parse_number(_txt(tds[1]))
        if val is None:
            continue

        # valeur forfaitaire repas standard (hors HCR)
        if "avantage en nature repas (1 repas)" in lib and "hcr" not in lib:
            repas_val = val
        # participation patronale maximum tickets restaurant
        if "participation patronale maximum sur tickets restaurant" in lib:
            titre_exo = val

    return {"repas": repas_val, "titre": titre_exo}

def scrape_logement() -> List[Dict]:
    r = requests.get(URL_LOGEMENT, timeout=25, headers={"User-Agent": UA})
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "lxml")

    header = None
    for h3 in soup.find_all("h3"):
        if "méthode de l’évaluation forfaitaire" in _txt(h3).lower() or \
           "methode de l’evaluation forfaitaire" in _txt(h3).lower() or \
           "méthode de l'evaluation forfaitaire" in _txt(h3).lower():
            header = h3
            break
    if not header:
        return []

    table = header.find_next("table")
    if not table:
        return []

    tbody = table.find("tbody") or table
    rows = tbody.find_all("tr")
    if len(rows) < 3:
        return []

    # structure attendue : 3 lignes (tranches / 1 pièce / par pièce suppl.)
    tranches = rows[0].find_all("td")[1:]
    v1 = rows[1].find_all("td")[1:]
    vpp = rows[2].find_all("td")[1:]

    out: List[Dict] = []
    for i in range(min(len(tranches), len(v1), len(vpp))):
        tranche_txt = _txt(tranches[i])
        # dernière valeur numérique de la tranche = plafond (sinon inf)
        nums = re.findall(r"(\d[\d\s\u202f\u00a0\.,]*)", tranche_txt)
        rem_max = parse_number(nums[-1]) if nums else None
        out.append({
            "remuneration_max_eur": rem_max if rem_max is not None else float("inf"),
            "valeur_1_piece_eur": parse_number(_txt(v1[i])),
            "valeur_par_piece_suppl_eur": parse_number(_txt(vpp[i])),
        })

    # filtre les lignes incomplètes
    out = [
        b for b in out
        if b["valeur_1_piece_eur"] is not None and b["valeur_par_piece_suppl_eur"] is not None
    ]
    return out

# ---------- main ----------
if __name__ == "__main__":
    try:
        repas = scrape_repas()
        logement = scrape_logement()

        payload = make_payload(
            repas=repas.get("repas"),
            titre_restaurant=repas.get("titre"),
            logement_bareme=logement,
        )

        # succès si on a au moins repas ET titre_restaurant ET >=1 tranche logement
        ok = payload["items"][0]["value"] is not None \
             and payload["items"][1]["value"] is not None \
             and isinstance(payload["items"][2]["value"], list) \
             and len(payload["items"][2]["value"]) > 0

        print(json.dumps(payload, ensure_ascii=False))
        sys.exit(0 if ok else 2)
    except Exception:
        # en échec, renvoyer structure vide mais valide
        empty = make_payload(None, None, [])
        print(json.dumps(empty, ensure_ascii=False))
        sys.exit(2)
