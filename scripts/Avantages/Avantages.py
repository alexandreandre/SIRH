# scripts/Avantages/Avantages.py

import json
import re
import requests
from bs4 import BeautifulSoup
from typing import Optional, List, Dict

URL_URSSAF = "https://www.urssaf.fr/accueil/outils-documentation/taux-baremes/avantages-en-nature.html"
UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

# -------- Helpers --------
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
            .replace(",", ".")
            .strip()
    )
    m = re.search(r"(-?\d+(?:\.\d+)?)", cleaned)
    return float(m.group(1)) if m else None

def make_payload(repas: Optional[float], titre_restaurant: Optional[float], logement: List[Dict]) -> dict:
    return {
        "id": "avantages_en_nature",
        "type": "param_bundle",
        "items": [
            {"key": "repas_valeur_forfaitaire_eur", "value": repas},
            {"key": "titre_restaurant_exoneration_max_eur", "value": titre_restaurant},
            {"key": "logement_bareme_forfaitaire", "value": logement},
        ],
        "meta": {
            "source": [{"url": URL_URSSAF, "label": "URSSAF", "date_doc": ""}],
            "generator": "scripts/Avantages/Avantages.py",
        },
    }

# -------- Scraper --------
def run() -> dict:
    r = requests.get(URL_URSSAF, timeout=25, headers={"User-Agent": UA})
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "lxml")

    repas_val: Optional[float] = None
    tr_exo: Optional[float] = None
    logement_bareme: List[Dict] = []

    # --- Repas ---
    repas_h = soup.find(id=lambda x: x and "repas" in x.lower())
    if not repas_h:
        repas_h = soup.find(lambda t: t.name in ("h2", "h3") and "repas" in _txt(t).lower())
    if repas_h:
        tbl = repas_h.find_next("table")
        if tbl:
            for tr in tbl.find_all("tr"):
                th = tr.find("th")
                if th and re.search(r"(?:^|\b)(1\s*repas|par\s*repas|valeur\s*forfaitaire)", _txt(th), re.I):
                    td = tr.find("td")
                    if td:
                        repas_val = parse_number(_txt(td))
                        break

    # --- Titres-restaurant (exonération maximale) ---
    tr_h = soup.find(id=lambda x: x and "titre" in x.lower())
    if not tr_h:
        tr_h = soup.find(lambda t: t.name in ("h2", "h3") and "titre-restaurant" in _txt(t).lower())
    if tr_h:
        tbl = tr_h.find_next("table")
        if tbl:
            th = tbl.find(lambda t: t.name == "th" and "exonération" in _txt(t).lower())
            if th:
                row = th.find_parent("tr")
                if row:
                    td = row.find("td")
                    if td:
                        tr_exo = parse_number(_txt(td))

    # --- Logement (barème forfaitaire) ---
    log_h = soup.find(id=lambda x: x and "logement" in x.lower())
    if not log_h:
        log_h = soup.find(lambda t: t.name in ("h2", "h3") and "logement" in _txt(t).lower())
    if log_h:
        tbl = log_h.find_next("table")
        if tbl:
            tbody = tbl.find("tbody") or tbl
            for tr in tbody.find_all("tr"):
                tds = tr.find_all(["th", "td"])
                if len(tds) < 3:
                    continue
                tranche_txt = _txt(tds[0]).lower()

                nums = re.findall(r"(\d[\d\s\u202f\u00a0,.]*)\s*€?", tranche_txt)
                rem_max = None
                if nums:
                    rem_max = parse_number(nums[-1])

                v1p = parse_number(_txt(tds[1]))
                vpp = parse_number(_txt(tds[2]))
                if v1p is not None and vpp is not None:
                    logement_bareme.append({
                        "remuneration_max_eur": rem_max,
                        "valeur_1_piece_eur": v1p,
                        "valeur_par_piece_suppl_eur": vpp,
                    })

    return make_payload(repas_val, tr_exo, logement_bareme)

if __name__ == "__main__":
    try:
        print(json.dumps(run(), ensure_ascii=False))
    except Exception:
        print(json.dumps(make_payload(None, None, []), ensure_ascii=False))
