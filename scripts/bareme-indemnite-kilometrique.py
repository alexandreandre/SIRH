# scripts/bareme-indemnite-kilometrique.py

import json
import re
import requests
from bs4 import BeautifulSoup
from pathlib import Path
from typing import Optional, Tuple, List, Dict

URL = "https://www.service-public.fr/particuliers/actualites/A14686"
FICHIER_TAUX = "config/taux_cotisations.json"

NBSP = "\xa0"
NNBSP = "\u202f"
THIN = "\u2009"

def _clean_number(s: str) -> float:
    s = s.strip().replace(NBSP, "").replace(NNBSP, "").replace(THIN, "").replace(" ", "")
    s = s.replace(",", ".")
    m = re.search(r"-?\d+(?:\.\d+)?", s)
    return float(m.group(0)) if m else 0.0

def parse_formula(txt: str) -> Tuple[float, float]:
    # "d x 0,529" -> (0.529, 0.0) ; "(d x 0,316) + 1 065" -> (0.316, 1065.0)
    s = txt.lower()
    for ch in (NBSP, NNBSP, THIN):
        s = s.replace(ch, " ")
    s = s.replace("×", "x").replace("(", "").replace(")", "")
    m_a = re.search(r"d\s*[x*]\s*([0-9]+(?:[ ,]\d+)*)", s)
    a = _clean_number(m_a.group(1)) if m_a else 0.0
    m_b = re.search(r"\+\s*([0-9][0-9 \u00A0\u202F\u2009]*)", s)
    b = _clean_number(m_b.group(1)) if m_b else 0.0
    return round(a, 3), round(b, 3)

def parse_cv_label_voiture(label: str) -> Tuple[Optional[int], Optional[int]]:
    # "3 CV et moins" -> (None,3) ; "7 CV et plus" -> (7,None) ; "4 CV" -> (4,4)
    s = label.lower().replace(NBSP, " ").replace(NNBSP, " ").replace(THIN, " ")
    nums = re.findall(r"\d+", s)
    if not nums:
        return None, None
    n = int(nums[0])
    if "moins" in s:
        return None, n
    if "plus" in s:
        return n, None
    return n, n

def parse_cv_label_moto(label: str) -> Tuple[Optional[int], Optional[int]]:
    # "1 ou 2 CV" -> (1,2) ; "3, 4 ou 5 CV" -> (3,5) ; "plus de 5 CV" -> (6,None)
    s = label.lower().replace(NBSP, " ").replace(NNBSP, " ").replace(THIN, " ")
    nums = [int(x) for x in re.findall(r"\d+", s)]
    if "plus de" in s and nums:
        return nums[0] + 1, None
    if "ou" in s and len(nums) >= 2:
        return min(nums), max(nums)
    if nums:
        return nums[0], nums[0]
    return None, None

def find_table_by_caption(soup: BeautifulSoup, contains: str) -> Optional[BeautifulSoup]:
    for tbl in soup.find_all("table"):
        cap = tbl.find("caption")
        if cap and contains in cap.get_text(" ", strip=True).lower():
            return tbl
    return None

def scrape_voitures(soup: BeautifulSoup) -> List[Dict]:
    tbl = find_table_by_caption(soup, "kilométrique applicable aux voitures")
    if tbl is None:
        tbl = soup.find("table", class_="sp-table")
    if tbl is None:
        raise ValueError("Tableau voitures introuvable.")
    rows = tbl.find("tbody").find_all("tr")
    out = []
    for tr in rows:
        th = tr.find("th")
        tds = tr.find_all("td")
        if not th or len(tds) < 3:
            continue
        cv_min, cv_max = parse_cv_label_voiture(th.get_text(" ", strip=True))
        a1, b1 = parse_formula(tds[0].get_text(" ", strip=True))
        a2, b2 = parse_formula(tds[1].get_text(" ", strip=True))
        a3, b3 = parse_formula(tds[2].get_text(" ", strip=True))
        out.append({
            "cv_min": cv_min, "cv_max": cv_max,
            "formules": [
                {"segment": 1, "a": a1, "b": b1},
                {"segment": 2, "a": a2, "b": b2},
                {"segment": 3, "a": a3, "b": b3},
            ]
        })
    if not out:
        raise ValueError("Données voitures vides.")
    return out

def scrape_moto(soup: BeautifulSoup) -> List[Dict]:
    tbl = find_table_by_caption(soup, "kilométrique applicable aux motocyclettes")
    if tbl is None:
        raise ValueError("Tableau motocyclettes introuvable.")
    rows = tbl.find("tbody").find_all("tr")
    out = []
    for tr in rows:
        th = tr.find("th")
        tds = tr.find_all("td")
        if not th or len(tds) < 3:
            continue
        cv_min, cv_max = parse_cv_label_moto(th.get_text(" ", strip=True))
        a1, b1 = parse_formula(tds[0].get_text(" ", strip=True))
        a2, b2 = parse_formula(tds[1].get_text(" ", strip=True))
        a3, b3 = parse_formula(tds[2].get_text(" ", strip=True))
        out.append({
            "cv_min": cv_min, "cv_max": cv_max,
            "formules": [
                {"segment": 1, "a": a1, "b": b1},
                {"segment": 2, "a": a2, "b": b2},
                {"segment": 3, "a": a3, "b": b3},
            ]
        })
    if not out:
        raise ValueError("Données motocyclettes vides.")
    return out

def scrape_cyclo(soup: BeautifulSoup) -> List[Dict]:
    tbl = find_table_by_caption(soup, "kilométrique applicable aux cyclomoteurs")
    if tbl is None:
        raise ValueError("Tableau cyclomoteurs introuvable.")
    rows = tbl.find("tbody").find_all("tr")
    if not rows:
        raise ValueError("Données cyclomoteurs vides.")
    # Une seule ligne de formules sans CV
    tds = rows[0].find_all("td")
    if len(tds) < 3:
        raise ValueError("Formules cyclomoteurs incomplètes.")
    a1, b1 = parse_formula(tds[0].get_text(" ", strip=True))
    a2, b2 = parse_formula(tds[1].get_text(" ", strip=True))
    a3, b3 = parse_formula(tds[2].get_text(" ", strip=True))
    return [{
        "cv_min": None, "cv_max": None,
        "formules": [
            {"segment": 1, "a": a1, "b": b1},
            {"segment": 2, "a": a2, "b": b2},
            {"segment": 3, "a": a3, "b": b3},
        ]
    }]

def update_json(tr_voitures: List[Dict], tr_moto: List[Dict], tr_cyclo: List[Dict]) -> None:
    path = Path(FICHIER_TAUX)
    if not path.exists():
        raise FileNotFoundError(f"Fichier introuvable: {FICHIER_TAUX}")
    with path.open("r", encoding="utf-8") as f:
        cfg = json.load(f)

    tc = cfg.setdefault("TAUX_COTISATIONS", {})

    tc["bareme_kilometrique_voitures_2025"] = {
        "libelle": "Barème kilométrique voitures 2025 (Service-Public)",
        "base": "distance_km",
        "segments": [
            {"d_min": 0, "d_max": 5000},
            {"d_min": 5001, "d_max": 20000},
            {"d_min": 20001, "d_max": None}
        ],
        "tranches_cv": tr_voitures
    }

    tc["bareme_kilometrique_motocyclettes_2025"] = {
        "libelle": "Barème kilométrique motocyclettes 2025 (Service-Public)",
        "base": "distance_km",
        "segments": [
            {"d_min": 0, "d_max": 3000},
            {"d_min": 3001, "d_max": 6000},
            {"d_min": 6001, "d_max": None}
        ],
        "tranches_cv": tr_moto
    }

    tc["bareme_kilometrique_cyclomoteurs_2025"] = {
        "libelle": "Barème kilométrique cyclomoteurs 2025 (Service-Public)",
        "base": "distance_km",
        "segments": [
            {"d_min": 0, "d_max": 3000},
            {"d_min": 3001, "d_max": 6000},
            {"d_min": 6001, "d_max": None}
        ],
        "tranches_cv": tr_cyclo
    }

    with path.open("w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)
    print("OK: JSON mis à jour (voitures, motos, cyclomoteurs)")

if __name__ == "__main__":
    try:
        r = requests.get(URL, timeout=25, headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "lxml")
        tr_voitures = scrape_voitures(soup)
        tr_moto = scrape_moto(soup)
        tr_cyclo = scrape_cyclo(soup)
        update_json(tr_voitures, tr_moto, tr_cyclo)
    except Exception as e:
        print(f"ERREUR: {e}")
