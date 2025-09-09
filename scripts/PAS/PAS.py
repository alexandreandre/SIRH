# scripts/PAS/PAS.py

import json
import re
import sys
from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup

URL_BOFIP = "https://bofip.impots.gouv.fr/bofip/11255-PGP.html/identifiant%3DBOI-BAREME-000037-20250410"

NBSP = "\xa0"
NNBSP = "\u202f"
THIN = "\u2009"

# -------- Helpers --------
def iso_now() -> str:
    """Retourne la date et l'heure actuelles au format ISO 8601 UTC."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def _clean_amount(txt: str) -> float:
    s = txt.strip().replace(NBSP, "").replace(NNBSP, "").replace(THIN, "")
    s = s.replace(" ", "").replace(".", "").replace(",", ".")
    m = re.search(r"(\d+(?:\.\d+)?)", s)
    return float(m.group(1)) if m else 0.0

def _clean_percent(txt: str) -> float:
    s = txt.strip().replace(NBSP, "").replace(NNBSP, "").replace(THIN, "").replace(" ", "")
    s = s.replace("%", "").replace(",", ".")
    m = re.search(r"(\d+(?:\.\d+)?)", s)
    return round(float(m.group(1)) / 100.0, 5) if m else 0.0

def _upper_bound_from_label(label: str) -> float | None:
    low = label.lower()
    # Trouve tous les nombres (y compris ceux avec des espaces comme séparateurs de milliers)
    nums = re.findall(r"\d[\d\s\u00A0\u202F\u2009\.]*", label)
    if not nums:
        return None
    if "inférieure à" in low:
        return _clean_amount(nums[-1])
    if "supérieure ou égale" in low and "inférieure à" in low and len(nums) >= 2:
        return _clean_amount(nums[1])
    if "supérieure ou égale" in low and "inférieure à" not in low:
        return None # C'est la dernière tranche, sans plafond supérieur
    return _clean_amount(nums[-1])

def _extract_tranches_from_table(table: BeautifulSoup) -> list[dict]:
    tranches = []
    for tr in table.find_all("tr"):
        tds = tr.find_all(["td", "th"])
        if len(tds) < 2:
            continue
        label = tds[0].get_text(" ", strip=True)
        taux_txt = tds[1].get_text(" ", strip=True)
        if not label or "%" not in taux_txt:
            continue
        plafond = _upper_bound_from_label(label)
        taux = _clean_percent(taux_txt)
        tranches.append({"plafond": plafond, "taux": taux})
    return tranches

# -------- Scraper --------
def scrape_bofip(url: str = URL_BOFIP) -> dict:
    print(f"Scraping de l'URL du BOFIP : {url}", file=sys.stderr)
    r = requests.get(url, timeout=30, headers={"User-Agent": "Mozilla/5.0", "Accept-Language": "fr,en;q=0.8"})
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "lxml")

    zones = {
        "metropole": None,
        "guadeloupe_reunion_martinique": None,
        "guyane_mayotte": None,
    }

    for tbl in soup.find_all("table"):
        caption = (tbl.find("caption").get_text(" ", strip=True).lower() if tbl.find("caption") else "")
        if any(k in caption for k in ["métropole", "metropole", "hors de france"]):
            zones["metropole"] = _extract_tranches_from_table(tbl)
        elif any(k in caption for k in ["guadeloupe", "réunion", "reunion", "martinique"]):
            zones["guadeloupe_reunion_martinique"] = _extract_tranches_from_table(tbl)
        elif any(k in caption for k in ["guyane", "mayotte"]):
            zones["guyane_mayotte"] = _extract_tranches_from_table(tbl)

    if not zones["metropole"]:
        raise ValueError("Table pour la métropole non trouvée ou vide.")
    if not zones["guadeloupe_reunion_martinique"]:
        raise ValueError("Table pour Guadeloupe/Réunion/Martinique non trouvée ou vide.")
    if not zones["guyane_mayotte"]:
        raise ValueError("Table pour Guyane/Mayotte non trouvée ou vide.")

    print(
        f"  - Données extraites : {len(zones['metropole'])} tranches (métropole), "
        f"{len(zones['guadeloupe_reunion_martinique'])} (GRM), "
        f"{len(zones['guyane_mayotte'])} (GM).",
        file=sys.stderr
    )
    return zones

# -------- Main --------
def main():
    """Orchestre le scraping et génère la sortie JSON pour l'orchestrateur."""
    try:
        zones_data = scrape_bofip()
    except Exception as e:
        print(f"ERREUR CRITIQUE: Le scraping du PAS a échoué. Raison : {e}", file=sys.stderr)
        sys.exit(1)

    payload = {
        "id": "pas_taux_neutre",
        "type": "bareme_imposition",
        "libelle": "Prélèvement à la Source (PAS) - Grille de taux par défaut",
        "sections": zones_data,
        "meta": {
            "source": [{
                "url": URL_BOFIP,
                "label": "BOFIP - Barème du prélèvement à la source",
                "date_doc": ""
            }],
            "scraped_at": iso_now(),
            "generator": "scripts/PAS/PAS.py",
            "method": "primary"
        }
    }

    # Impression du JSON final sur la sortie standard
    print(json.dumps(payload, ensure_ascii=False))


if __name__ == "__main__":
    main()