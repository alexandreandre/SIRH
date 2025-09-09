# scripts/AGIRC-ARRCO/AGIRC-ARRCO.py

import json
import re
import sys
import requests
from bs4 import BeautifulSoup

URL_AGIRC_ARRCO = "https://www.agirc-arrco.fr/entreprises/mon-entreprise/calculer-et-declarer/le-calcul-des-cotisations-de-retraite-complementaire/"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"


# ----------------- Utils -----------------
def _txt(el) -> str:
    return el.get_text(" ", strip=True).lower() if el else ""


def _has_pct(s: str) -> bool:
    return bool(re.search(r"\d+(?:[.,]\d+)?\s*%", s))


def _parse_rate(txt: str) -> float | None:
    m = re.search(r"([0-9]+(?:[.,][0-9]+)?)\s*%", txt or "")
    if not m:
        return None
    v = float(m.group(1).replace(",", "."))
    return round(v / 100.0, 6)


def _is_table_retraite(tbl) -> bool:
    t = _txt(tbl)
    return ("taux de calcul des points" in t) and ("tranche 1" in t) and ("tranche 2" in t)


def _is_table_ceg(tbl) -> bool:
    t = _txt(tbl)
    # CEG sans CET
    return ("ceg" in t) and ("cet" not in t)


def _is_table_cet(tbl) -> bool:
    t = _txt(tbl)
    # CET sans CEG
    return ("cet" in t) and ("ceg" not in t)


def _is_table_apec(tbl) -> bool:
    head = _txt(tbl.find("thead"))
    body = _txt(tbl.find("tbody"))
    if ("assiette" in head and "tranche 1" in head and "tranche 2" in head and
            "part salariale" in body and "part patronale" in body):
        return True
    prev = tbl.find_previous(string=True)
    if prev and "apec" in (prev or "").strip().lower():
        return True
    if ("part salariale" in body) and ("part patronale" in body) and ("total" in body):
        return True
    return False


# ------------- Scraper -------------
def scrape_agirc_arrco() -> dict | None:
    try:
        r = requests.get(URL_AGIRC_ARRCO, timeout=25, headers={"User-Agent": UA})
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "lxml")

        results = {
            "retraite_comp_t1_salarial": None,
            "retraite_comp_t1_patronal": None,
            "retraite_comp_t2_salarial": None,
            "retraite_comp_t2_patronal": None,
            "ceg_t1_salarial": None,
            "ceg_t1_patronal": None,
            "ceg_t2_salarial": None,
            "ceg_t2_patronal": None,
            "cet_salarial": None,
            "cet_patronal": None,
            "apec_salarial": None,
            "apec_patronal": None,
        }

        tables = soup.find_all("table")

        for tbl in tables:
            body = tbl.find("tbody") or tbl
            rows = body.find_all("tr")

            # Retraite (points)
            if _is_table_retraite(tbl):
                for idx, tr in enumerate(rows):
                    row_txt = _txt(tr)
                    if "tranche 1" in row_txt:
                        target = rows[idx + 1] if (idx + 1 < len(rows) and not _has_pct(row_txt)) else tr
                        cells = target.find_all(["td", "th"])
                        rates = [_parse_rate(c.get_text()) for c in cells if _has_pct(_txt(c))]
                        if len(rates) >= 2:
                            results["retraite_comp_t1_salarial"] = rates[0]
                            results["retraite_comp_t1_patronal"] = rates[1]
                    if "tranche 2" in row_txt:
                        target = rows[idx + 1] if (idx + 1 < len(rows) and not _has_pct(row_txt)) else tr
                        cells = target.find_all(["td", "th"])
                        rates = [_parse_rate(c.get_text()) for c in cells if _has_pct(_txt(c))]
                        if len(rates) >= 2:
                            results["retraite_comp_t2_salarial"] = rates[0]
                            results["retraite_comp_t2_patronal"] = rates[1]
                continue

            # CEG
            if _is_table_ceg(tbl):
                for idx, tr in enumerate(rows):
                    row_txt = _txt(tr)
                    if "tranche 1" in row_txt:
                        target = rows[idx + 1] if (idx + 1 < len(rows) and not _has_pct(row_txt)) else tr
                        cells = target.find_all(["td", "th"])
                        rates = [_parse_rate(c.get_text()) for c in cells if _has_pct(_txt(c))]
                        if len(rates) >= 2:
                            results["ceg_t1_salarial"] = rates[0]
                            results["ceg_t1_patronal"] = rates[1]
                    if "tranche 2" in row_txt:
                        target = rows[idx + 1] if (idx + 1 < len(rows) and not _has_pct(row_txt)) else tr
                        cells = target.find_all(["td", "th"])
                        rates = [_parse_rate(c.get_text()) for c in cells if _has_pct(_txt(c))]
                        if len(rates) >= 2:
                            results["ceg_t2_salarial"] = rates[0]
                            results["ceg_t2_patronal"] = rates[1]
                continue

            # CET
            if _is_table_cet(tbl):
                chosen = None
                for tr in rows[::-1]:
                    if _has_pct(_txt(tr)):
                        tds = tr.find_all(["td", "th"])
                        if len(tds) >= 2:
                            chosen = tds
                            break
                if chosen:
                    rates = [_parse_rate(c.get_text()) for c in chosen if _has_pct(_txt(c))]
                    if len(rates) >= 2:
                        results["cet_salarial"] = rates[0]
                        results["cet_patronal"] = rates[1]
                continue

            # APEC
            if _is_table_apec(tbl):
                chosen = None
                for tr in rows:
                    if _has_pct(_txt(tr)):
                        tds = tr.find_all(["td", "th"])
                        if len(tds) >= 2:
                            chosen = tds
                            break
                if chosen:
                    rates = [_parse_rate(c.get_text()) for c in chosen if _has_pct(_txt(c))]
                    if len(rates) >= 2:
                        results["apec_salarial"] = rates[0]
                        results["apec_patronal"] = rates[1]
                continue

        # Validation complète (12 clés non None)
        if all(results[k] is not None for k in results):
            return results
        return None

    except Exception:
        return None


def make_payload(bundle: dict | None) -> dict:
    """
    Retourne un 'bundle' multi-cotisations prêt pour un orchestrateur.
    """
    items = []
    if bundle:
        items = [
            {
                "id": "retraite_comp_t1",
                "libelle": "Retraite Complémentaire Tranche 1 (AGIRC-ARRCO)",
                "base": "plafond_ss",
                "valeurs": {
                    "salarial": bundle["retraite_comp_t1_salarial"],
                    "patronal": bundle["retraite_comp_t1_patronal"],
                },
            },
            {
                "id": "retraite_comp_t2",
                "libelle": "Retraite Complémentaire Tranche 2 (AGIRC-ARRCO)",
                "base": "tranche_2",
                "valeurs": {
                    "salarial": bundle["retraite_comp_t2_salarial"],
                    "patronal": bundle["retraite_comp_t2_patronal"],
                },
            },
            {
                "id": "ceg_t1",
                "libelle": "Contribution d'Équilibre Général (CEG) T1",
                "base": "plafond_ss",
                "valeurs": {
                    "salarial": bundle["ceg_t1_salarial"],
                    "patronal": bundle["ceg_t1_patronal"],
                },
            },
            {
                "id": "ceg_t2",
                "libelle": "Contribution d'Équilibre Général (CEG) T2",
                "base": "tranche_2",
                "valeurs": {
                    "salarial": bundle["ceg_t2_salarial"],
                    "patronal": bundle["ceg_t2_patronal"],
                },
            },
            {
                "id": "cet",
                "libelle": "Contribution d'Équilibre Technique (CET)",
                "base": "brut_sup_plafond",
                "valeurs": {
                    "salarial": bundle["cet_salarial"],
                    "patronal": bundle["cet_patronal"],
                },
            },
            {
                "id": "apec",
                "libelle": "Cotisation APEC (Cadres)",
                "base": "brut_cadre_4_plafonds",
                "valeurs": {
                    "salarial": bundle["apec_salarial"],
                    "patronal": bundle["apec_patronal"],
                },
            },
        ]

    return {
        "id": "agirc_arrco_bundle",
        "type": "cotisation_bundle",
        "items": items,
        "meta": {
            "source": [{"url": URL_AGIRC_ARRCO, "label": "Agirc-Arrco", "date_doc": ""}],
            "generator": "scripts/AGIRC-ARRCO/AGIRC-ARRCO.py",
        },
    }


if __name__ == "__main__":
    data = scrape_agirc_arrco()
    payload = make_payload(data)
    print(json.dumps(payload, ensure_ascii=False))
    sys.exit(0 if data is not None else 2)
