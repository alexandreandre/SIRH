# scripts/bareme-indemnite-kilometrique/bareme-indemnite-kilometrique_LegiSocial.py

import json
import re
from datetime import datetime, timezone
from typing import Optional, Tuple, List, Dict

import requests
from bs4 import BeautifulSoup

URL = "https://www.legisocial.fr/reperes-sociaux/bareme-kilometrique-2025.html"

NBSP = "\xa0"
NNBSP = "\u202f"
THIN = "\u2009"


# ---------- Utils ----------
def iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


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

    m_a = re.search(r"d\s*[*x]\s*([-+]?\d+(?:[ \u00A0\u202F\u2009\.,]\d+)*)", s)
    a = _clean_number(m_a.group(1)) if m_a else None

    m_b = re.search(r"\+\s*([-+]?\d+(?:[ \u00A0\u202F\u2009\.,]\d+)*)", s)
    b = _clean_number(m_b.group(1)) if m_b else 0.0

    if a is not None:
        return round(a, 3), round(b, 3)

    nums = [_clean_number(x) for x in re.findall(r"[-+]?\d+(?:[ \u00A0\u202F\u2009\.,]\d+)*", s)]
    if not nums:
        return 0.0, 0.0
    if len(nums) == 1:
        return round(nums[0], 3), 0.0
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
        out.append(
            {
                "cv_min": cv_min,
                "cv_max": cv_max,
                "formules": [
                    {"segment": 1, "a": a1, "b": b1},
                    {"segment": 2, "a": a2, "b": b2},
                    {"segment": 3, "a": a3, "b": b3},
                ],
            }
        )
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
        out.append(
            {
                "cv_min": cv_min,
                "cv_max": cv_max,
                "formules": [
                    {"segment": 1, "a": a1, "b": b1},
                    {"segment": 2, "a": a2, "b": b2},
                    {"segment": 3, "a": a3, "b": b3},
                ],
            }
        )
    if not out:
        raise ValueError("Données motocyclettes vides.")
    return out


def scrape_cyclo(soup: BeautifulSoup) -> List[Dict]:
    tbl = _find_table_by_banner(soup, "tarif applicable aux cyclomoteurs")
    if tbl is None:
        raise ValueError("Table LégiSocial cyclomoteurs introuvable.")

    rows = tbl.find_all("tr")
    for tr in rows:
        tds = tr.find_all("td")
        if len(tds) != 3:
            continue
        cols = [td.get_text(" ", strip=True) for td in tds]
        if all(("d" in c.lower() and re.search(r"\d", c)) for c in cols):
            a1, b1 = parse_formula(cols[0])
            a2, b2 = parse_formula(cols[1])
            a3, b3 = parse_formula(cols[2])
            return [
                {
                    "cv_min": None,
                    "cv_max": None,
                    "formules": [
                        {"segment": 1, "a": a1, "b": b1},
                        {"segment": 2, "a": a2, "b": b2},
                        {"segment": 3, "a": a3, "b": b3},
                    ],
                }
            ]

    raise ValueError("Formules cyclomoteurs introuvables dans le tableau ciblé.")


# ---------- Payload ----------
def build_payload(voitures: List[Dict], motos: List[Dict], cyclos: List[Dict]) -> dict:
    return {
        "id": "baremes_km",
        "type": "barème_kilométrique",
        "libelle": "Barème kilométrique 2025 (LégiSocial)",
        "annee": 2025,
        "vehicules": {
            "voitures": {
                "base": "distance_km",
                "segments": [
                    {"d_min": 0, "d_max": 5000},
                    {"d_min": 5001, "d_max": 20000},
                    {"d_min": 20001, "d_max": None},
                ],
                "tranches_cv": voitures,
            },
            "motocyclettes": {
                "base": "distance_km",
                "segments": [
                    {"d_min": 0, "d_max": 3000},
                    {"d_min": 3001, "d_max": 6000},
                    {"d_min": 6001, "d_max": None},
                ],
                "tranches_cv": motos,
            },
            "cyclomoteurs": {
                "base": "distance_km",
                "segments": [
                    {"d_min": 0, "d_max": 3000},
                    {"d_min": 3001, "d_max": 6000},
                    {"d_min": 6001, "d_max": None},
                ],
                "tranches_cv": cyclos,
            },
        },
        "meta": {
            "source": [{"url": URL, "label": "LégiSocial", "date_doc": ""}],
            "scraped_at": iso_now(),
            "generator": "scripts/bareme-indemnite-kilometrique/bareme-indemnite-kilometrique_LegiSocial.py",
            "method": "secondary",
        },
    }


# ---------- Main ----------
if __name__ == "__main__":
    r = requests.get(URL, timeout=25, headers={"User-Agent": "Mozilla/5.0"})
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "lxml")

    tr_voitures = scrape_voitures(soup)
    tr_moto = scrape_moto(soup)
    tr_cyclo = scrape_cyclo(soup)

    payload = build_payload(tr_voitures, tr_moto, tr_cyclo)
    print(json.dumps(payload, ensure_ascii=False))
