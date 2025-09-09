# scripts/PAS.py

import json
import re
import requests
from bs4 import BeautifulSoup
from pathlib import Path

FICHIER_TAUX = 'config/taux_cotisations.json'
URL_BOFIP = "https://bofip.impots.gouv.fr/bofip/11255-PGP.html/identifiant%3DBOI-BAREME-000037-20250410"

NBSP = "\xa0"
NNBSP = "\u202f"
THIN = "\u2009"

# -------- Helpers --------
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
    nums = re.findall(r"\d[\d\s\u00A0\u202F\u2009\.]*", label)
    if not nums:
        return None
    if "inférieure à" in low:
        return _clean_amount(nums[-1])
    if "supérieure ou égale" in low and "inférieure à" in low and len(nums) >= 2:
        return _clean_amount(nums[1])
    if "supérieure ou égale" in low and "inférieure à" not in low:
        return None
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
    return tranches  # pas de décalage

# -------- Scraper --------
def scrape_bofip(url: str = URL_BOFIP) -> dict:
    print(f"Scraping: {url}")
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
        raise ValueError("Table métropole non trouvée ou vide.")
    if not zones["guadeloupe_reunion_martinique"]:
        raise ValueError("Table Guadeloupe/Réunion/Martinique non trouvée ou vide.")
    if not zones["guyane_mayotte"]:
        raise ValueError("Table Guyane/Mayotte non trouvée ou vide.")

    print(
        f"OK: {len(zones['metropole'])} métropole, "
        f"{len(zones['guadeloupe_reunion_martinique'])} GRM, "
        f"{len(zones['guyane_mayotte'])} GM."
    )
    return zones

# -------- Update JSON --------
def update_config_with_pas(zones: dict, fichier: str = FICHIER_TAUX) -> None:
    path = Path(fichier)
    if not path.exists():
        raise FileNotFoundError(f"Fichier introuvable: {fichier}")

    with path.open("r", encoding="utf-8") as f:
        config = json.load(f)

    tc = config.setdefault("TAUX_COTISATIONS", {})

    tc["pas_bareme_taux_neutre_2025"] = {
        "libelle": "Barème taux neutre PAS 2025 (mensuel, métropole)",
        "base": "net_imposable_mensuel",
        "tranches": zones["metropole"],
    }
    tc["pas_bareme_taux_neutre_2025_outremer_grm"] = {
        "libelle": "Barème taux neutre PAS 2025 (Guadeloupe, Réunion, Martinique)",
        "base": "net_imposable_mensuel",
        "tranches": zones["guadeloupe_reunion_martinique"],
    }
    tc["pas_bareme_taux_neutre_2025_outremer_gm"] = {
        "libelle": "Barème taux neutre PAS 2025 (Guyane, Mayotte)",
        "base": "net_imposable_mensuel",
        "tranches": zones["guyane_mayotte"],
    }

    with path.open("w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)
    print("✅ JSON mis à jour.")

# -------- Main --------
if __name__ == "__main__":
    try:
        zones = scrape_bofip()
        update_config_with_pas(zones)
    except Exception as e:
        print(f"ERREUR: {e}")
