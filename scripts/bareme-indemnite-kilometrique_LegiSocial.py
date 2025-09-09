# scripts/bareme-indemnite-kilometrique_LegiSocial.py

import json
import re
import requests
from bs4 import BeautifulSoup
from pathlib import Path
from typing import Optional, Tuple, List, Dict

URL = "https://www.legisocial.fr/reperes-sociaux/bareme-kilometrique-2025.html"
FICHIER_TAUX = "config/taux_cotisations.json"

NBSP = "\xa0"
NNBSP = "\u202f"
THIN = "\u2009"

# ---------- Utils ----------
def _clean_number(s: str) -> float:
    s = s.strip().replace(NBSP, "").replace(NNBSP, "").replace(THIN, "").replace(" ", "")
    # LégiSocial : décimales avec virgule, milliers avec point
    s = s.replace(".", "").replace(",", ".")
    m = re.search(r"-?\d+(?:\.\d+)?", s)
    return float(m.group(0)) if m else 0.0

def parse_formula(txt: str) -> Tuple[float, float]:
    """
    "d * 0,315" -> (0.315, 0.0)
    "(d * 0,079) + 711" -> (0.079, 711.0)
    Tolérant aux espaces, ×, x, *, () et séparateurs.
    """
    s = txt.lower()
    for ch in (NBSP, NNBSP, THIN):
        s = s.replace(ch, " ")
    s = s.replace("×", "x").replace("·", "*").replace("(", "").replace(")", "").strip()

    # a) extraction robuste du coefficient devant d
    m_a = re.search(r"d\s*[*x]\s*([-+]?\d+(?:[ \u00A0\u202F\u2009\.,]\d+)*)", s)
    a = _clean_number(m_a.group(1)) if m_a else None

    # b) intercept optionnel
    m_b = re.search(r"\+\s*([-+]?\d+(?:[ \u00A0\u202F\u2009\.,]\d+)*)", s)
    b = _clean_number(m_b.group(1)) if m_b else 0.0

    if a is not None:
        return round(a, 3), round(b, 3)

    # Fallback ultra-tolérant si le motif n'a pas matché
    nums = [ _clean_number(x) for x in re.findall(r"[-+]?\d+(?:[ \u00A0\u202F\u2009\.,]\d+)*", s) ]
    if not nums:
        return 0.0, 0.0
    if len(nums) == 1:
        return round(nums[0], 3), 0.0
    # Heuristique : le plus petit = coefficient, le plus grand = intercept
    a_guess = min(nums)
    b_guess = max(nums)
    return round(a_guess, 3), round(b_guess, 3)

def parse_cv_label_voiture(label: str) -> Tuple[Optional[int], Optional[int]]:
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
    s = label.lower().replace(NBSP, " ").replace(NNBSP, " ").replace(THIN, " ")
    nums = [int(x) for x in re.findall(r"\d+", s)]
    if "plus de" in s and nums:
        return nums[0] + 1, None
    if "ou" in s and len(nums) >= 2:
        return min(nums), max(nums)
    if nums:
        return nums[0], nums[0]
    return None, None

def _find_table_by_banner(soup: BeautifulSoup, needle: str) -> Optional[BeautifulSoup]:
    nd = needle.lower()
    for tbl in soup.find_all("table"):
        txt = tbl.get_text(" ", strip=True).lower()
        if nd in txt:
            return tbl
    return None

# ---------- Parsers ----------
def scrape_voitures(soup: BeautifulSoup) -> List[Dict]:
    tbl = _find_table_by_banner(soup, "tarif applicable aux automobiles")
    if tbl is None:
        raise ValueError("Table LégiSocial voitures introuvable.")
    rows = tbl.find_all("tr")
    out: List[Dict] = []
    for tr in rows:
        tds = tr.find_all("td")
        if len(tds) != 4:
            continue
        label = tds[0].get_text(" ", strip=True)
        if "cv" not in label.lower():
            continue
        a1, b1 = parse_formula(tds[1].get_text(" ", strip=True))
        a2, b2 = parse_formula(tds[2].get_text(" ", strip=True))
        a3, b3 = parse_formula(tds[3].get_text(" ", strip=True))
        cv_min, cv_max = parse_cv_label_voiture(label)
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
    tbl = _find_table_by_banner(soup, "tarif applicable aux motocyclettes")
    if tbl is None:
        raise ValueError("Table LégiSocial motocyclettes introuvable.")
    rows = tbl.find_all("tr")
    out: List[Dict] = []
    for tr in rows:
        tds = tr.find_all("td")
        if len(tds) != 4:
            continue
        label = tds[0].get_text(" ", strip=True)
        if "cv" not in label.lower():
            continue
        a1, b1 = parse_formula(tds[1].get_text(" ", strip=True))
        a2, b2 = parse_formula(tds[2].get_text(" ", strip=True))
        a3, b3 = parse_formula(tds[3].get_text(" ", strip=True))
        cv_min, cv_max = parse_cv_label_moto(label)
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
    tbl = _find_table_by_banner(soup, "tarif applicable aux cyclomoteurs")
    if tbl is None:
        raise ValueError("Table LégiSocial cyclomoteurs introuvable.")

    # Cherche une ligne avec exactement 3 <td> contenant chacune une formule avec 'd'
    rows = tbl.find_all("tr")
    for tr in rows:
        tds = tr.find_all("td")
        if len(tds) != 3:
            continue
        cols = [td.get_text(" ", strip=True) for td in tds]
        # toutes les colonnes doivent ressembler à une formule: présence de 'd' et d'un nombre
        if all(("d" in c.lower() and re.search(r"\d", c)) for c in cols):
            a1, b1 = parse_formula(cols[0])
            a2, b2 = parse_formula(cols[1])
            a3, b3 = parse_formula(cols[2])
            return [{
                "cv_min": None, "cv_max": None,
                "formules": [
                    {"segment": 1, "a": a1, "b": b1},
                    {"segment": 2, "a": a2, "b": b2},
                    {"segment": 3, "a": a3, "b": b3},
                ]
            }]

    raise ValueError("Formules cyclomoteurs introuvables dans le tableau ciblé.")

# ---------- JSON update ----------
def update_existing_keys(tr_voitures: List[Dict], tr_moto: List[Dict], tr_cyclo: List[Dict]) -> None:
    path = Path(FICHIER_TAUX)
    if not path.exists():
        raise FileNotFoundError(f"Fichier introuvable: {FICHIER_TAUX}")

    cfg = json.loads(path.read_text(encoding="utf-8"))
    tc = cfg.get("TAUX_COTISATIONS")
    if not isinstance(tc, dict):
        raise ValueError("Clé TAUX_COTISATIONS manquante.")

    required = [
        "bareme_kilometrique_voitures_2025",
        "bareme_kilometrique_motocyclettes_2025",
        "bareme_kilometrique_cyclomoteurs_2025",
    ]
    for k in required:
        if k not in tc:
            raise KeyError(f"Clé manquante: {k}")

    tc["bareme_kilometrique_voitures_2025"]["tranches_cv"] = tr_voitures
    tc["bareme_kilometrique_motocyclettes_2025"]["tranches_cv"] = tr_moto
    tc["bareme_kilometrique_cyclomoteurs_2025"]["tranches_cv"] = tr_cyclo

    path.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")
    print("✅ JSON mis à jour depuis LégiSocial (voitures, motos, cyclomoteurs).")

# ---------- Main ----------
if __name__ == "__main__":
    try:
        r = requests.get(URL, timeout=25, headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "lxml")

        tr_voitures = scrape_voitures(soup)
        tr_moto = scrape_moto(soup)
        tr_cyclo = scrape_cyclo(soup)

        update_existing_keys(tr_voitures, tr_moto, tr_cyclo)
    except Exception as e:
        print(f"ERREUR: {e}")
