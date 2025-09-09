# scripts/AGIRC-ARRCO/AGIRC-ARRCO_LegiSocial.py

import json
import re
import sys
import requests
from bs4 import BeautifulSoup
from typing import Dict, Optional, List

URL_LEGISOCIAL = "https://www.legisocial.fr/reperes-sociaux/cotisations-agirc-arrco-2025.html"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"

# ---------- helpers ----------
def _txt(el) -> str:
    return el.get_text(" ", strip=True) if el else ""

def _norm(s: str) -> str:
    return (s or "").replace("\u202f", " ").replace("\xa0", " ").lower().strip()

def _has_pct(s: str) -> bool:
    return bool(re.search(r"\d+\s*(?:[.,]\s*\d+)?\s*%", s or ""))

def parse_taux(text: str) -> Optional[float]:
    """'3,15 %' -> 0.0315"""
    if not text:
        return None
    try:
        cleaned = (
            text.replace("\u202f", "")
            .replace("\xa0", "")
            .replace(" ", "")
            .replace(",", ".")
            .replace("%", "")
            .strip()
        )
        return round(float(cleaned) / 100.0, 5)
    except ValueError:
        return None

def _extract_row_pcts(tr) -> List[float]:
    vals: List[float] = []
    for td in tr.find_all(["td", "th"]):
        t = _txt(td)
        if _has_pct(t):
            v = parse_taux(t)
            if v is not None:
                vals.append(v)
    return vals

def _is_tot_statut_table(tbl) -> bool:
    # Table contenant Retraite (T1/T2), CEG (T1/T2), CET
    t = _norm(_txt(tbl))
    return any(k in t for k in ["retraite tranche 1", "retraite tranche 2", "ceg", "cet"])

def _is_cadres_table(tbl) -> bool:
    # Table contenant APEC
    t = _norm(_txt(tbl))
    return "apec" in t

def mk_item(_id: str, libelle: str, base: str, sal: float, pat: float) -> Dict:
    return {
        "id": _id,
        "type": "cotisation",
        "libelle": libelle,
        "base": base,
        "valeurs": {"salarial": sal, "patronal": pat}
    }

# ---------- scrape ----------
def scrape_legisocial() -> Optional[Dict[str, float]]:
    try:
        r = requests.get(URL_LEGISOCIAL, timeout=25, headers={"User-Agent": UA})
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "lxml")
    except Exception as e:
        print(f"[ERREUR] HTTP: {e}", file=sys.stderr)
        return None

    taux: Dict[str, float] = {}
    tables = soup.find_all("table")

    # 1) Retraite T1/T2, CEG T1/T2, CET
    for tbl in tables:
        if not _is_tot_statut_table(tbl):
            continue
        for tr in tbl.find_all("tr"):
            row = _norm(_txt(tr))

            if "retraite tranche 1" in row:
                p = _extract_row_pcts(tr)
                if len(p) >= 3:
                    taux["retraite_comp_t1_salarial"] = p[-2]
                    taux["retraite_comp_t1_patronal"] = p[-1]
                elif len(p) >= 2:
                    taux["retraite_comp_t1_salarial"] = p[0]
                    taux["retraite_comp_t1_patronal"] = p[1]

            elif "retraite tranche 2" in row:
                p = _extract_row_pcts(tr)
                if len(p) >= 3:
                    taux["retraite_comp_t2_salarial"] = p[-2]
                    taux["retraite_comp_t2_patronal"] = p[-1]
                elif len(p) >= 2:
                    taux["retraite_comp_t2_salarial"] = p[0]
                    taux["retraite_comp_t2_patronal"] = p[1]

            elif "ceg" in row and "tranche 1" in row:
                p = _extract_row_pcts(tr)
                if len(p) >= 3:
                    taux["ceg_t1_salarial"] = p[-2]
                    taux["ceg_t1_patronal"] = p[-1]
                elif len(p) >= 2:
                    taux["ceg_t1_salarial"] = p[0]
                    taux["ceg_t1_patronal"] = p[1]

            elif "ceg" in row and "tranche 2" in row:
                p = _extract_row_pcts(tr)
                if len(p) >= 3:
                    taux["ceg_t2_salarial"] = p[-2]
                    taux["ceg_t2_patronal"] = p[-1]
                elif len(p) >= 2:
                    taux["ceg_t2_salarial"] = p[0]
                    taux["ceg_t2_patronal"] = p[1]

            elif "cet" in row:
                p = _extract_row_pcts(tr)
                if "cet_salarial" not in taux and len(p) >= 2:
                    if len(p) >= 3:
                        taux["cet_salarial"] = p[-2]
                        taux["cet_patronal"] = p[-1]
                    else:
                        taux["cet_salarial"] = p[0]
                        taux["cet_patronal"] = p[1]

    # 2) APEC
    for tbl in tables:
        if not _is_cadres_table(tbl):
            continue
        for tr in tbl.find_all("tr"):
            row = _norm(_txt(tr))
            if "apec" in row:
                p = _extract_row_pcts(tr)
                if len(p) >= 3:
                    taux["apec_salarial"] = p[-2]
                    taux["apec_patronal"] = p[-1]
                elif len(p) >= 2:
                    taux["apec_salarial"] = p[0]
                    taux["apec_patronal"] = p[1]
                break

    # contrôle complétude
    expected = [
        "retraite_comp_t1_salarial", "retraite_comp_t1_patronal",
        "retraite_comp_t2_salarial", "retraite_comp_t2_patronal",
        "ceg_t1_salarial", "ceg_t1_patronal",
        "ceg_t2_salarial", "ceg_t2_patronal",
        "cet_salarial", "cet_patronal",
        "apec_salarial", "apec_patronal",
    ]
    missing = [k for k in expected if k not in taux or taux[k] is None]
    if missing:
        print(f"[ERREUR] Taux manquants: {missing}", file=sys.stderr)
        return None

    return taux

# ---------- main ----------
if __name__ == "__main__":
    tx = scrape_legisocial()
    if not tx:
        # échoue proprement pour l'orchestrateur
        print(
            json.dumps(
                {
                    "id": "agirc_arrco_bundle",
                    "type": "cotisation_bundle",
                    "items": [],
                    "meta": {
                        "source": [{"url": URL_LEGISOCIAL, "label": "LegiSocial", "date_doc": ""}],
                        "generator": "scripts/AGIRC-ARRCO/AGIRC-ARRCO_LegiSocial.py",
                    },
                },
                ensure_ascii=False,
            )
        )
        sys.exit(2)

    items = [
        mk_item("retraite_comp_t1", "Retraite Complémentaire Tranche 1 (AGIRC-ARRCO)", "plafond_ss", tx["retraite_comp_t1_salarial"], tx["retraite_comp_t1_patronal"]),
        mk_item("retraite_comp_t2", "Retraite Complémentaire Tranche 2 (AGIRC-ARRCO)", "tranche_2", tx["retraite_comp_t2_salarial"], tx["retraite_comp_t2_patronal"]),
        mk_item("ceg_t1", "Contribution d'Équilibre Général (CEG) T1", "plafond_ss", tx["ceg_t1_salarial"], tx["ceg_t1_patronal"]),
        mk_item("ceg_t2", "Contribution d'Équilibre Général (CEG) T2", "tranche_2", tx["ceg_t2_salarial"], tx["ceg_t2_patronal"]),
        mk_item("cet", "Contribution d'Équilibre Technique (CET)", "brut_sup_plafond", tx["cet_salarial"], tx["cet_patronal"]),
        mk_item("apec", "Cotisation APEC (Cadres)", "brut_cadre_4_plafonds", tx["apec_salarial"], tx["apec_patronal"]),
    ]

    bundle = {
        "id": "agirc_arrco_bundle",
        "type": "cotisation_bundle",
        "items": items,
        "meta": {
            "source": [{"url": URL_LEGISOCIAL, "label": "LegiSocial", "date_doc": ""}],
            "generator": "scripts/AGIRC-ARRCO/AGIRC-ARRCO_LegiSocial.py",
        },
    }
    print(json.dumps(bundle, ensure_ascii=False))
    sys.exit(0)
