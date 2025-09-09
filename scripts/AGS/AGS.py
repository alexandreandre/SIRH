# scripts/AGS/AGS.py

import json
import os
import re
import sys
import requests
from bs4 import BeautifulSoup

FICHIER_ENTREPRISE = 'config/parametres_entreprise.json'
URL_URSSAF = "https://www.urssaf.fr/accueil/outils-documentation/taux-baremes/taux-cotisations-secteur-prive.html"
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"


def _norm_txt(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip()


def _parse_percent(s: str) -> float | None:
    m = re.search(r"([0-9]+(?:[.,][0-9]+)?)\s*%", s)
    if not m:
        return None
    v = float(m.group(1).replace(",", "."))
    return round(v / 100.0, 6)


def _extract_rate_from_value_text(value_text: str, is_ett: bool) -> float | None:
    """
    value_text contient généralement 2 pourcentages, ex.:
    "0,20 % (0,21 % pour les entreprises de travail temporaire)"
    - général = premier %
    - ETT = % précédé/suivi de 'entreprises de travail temporaire' (ou 'ETT')
    """
    txt = _norm_txt(value_text)

    if is_ett:
        # Cherche un % associé à "entreprises de travail temporaire" ou "ETT" dans ~80 chars suivants
        patt_ett = re.compile(
            r"([0-9]+(?:[.,][0-9]+)?)\s*%(?=[^%]{0,120}\b(entreprises?\s+de\s+travail\s+temporaire|ETT)\b)",
            re.IGNORECASE,
        )
        m = patt_ett.search(txt)
        if m:
            return round(float(m.group(1).replace(",", ".")) / 100.0, 6)
        # fallback: si 2 taux, on prend le dernier
        all_rates = re.findall(r"([0-9]+(?:[.,][0-9]+)?)\s*%", txt)
        if all_rates:
            return round(float(all_rates[-1].replace(",", ".")) / 100.0, 6)
        return None
    else:
        # Retire les segments évoquant ETT pour éviter de capter le mauvais %
        txt_no_ett = re.sub(r"\([^)]*(entreprises?\s+de\s+travail\s+temporaire|ETT)[^)]*\)", " ", txt, flags=re.IGNORECASE)
        m = re.search(r"([0-9]+(?:[.,][0-9]+)?)\s*%", txt_no_ett)
        if m:
            return round(float(m.group(1).replace(",", ".")) / 100.0, 6)
        # fallback: premier % du texte complet
        return _parse_percent(txt)


def get_taux_ags(is_ett: bool) -> float | None:
    try:
        r = requests.get(URL_URSSAF, timeout=25, headers={"User-Agent": UA})
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")

        # Section "Taux de cotisations employeur"
        employeur_section = None
        for article in soup.find_all('article'):
            h2 = article.find('h2', class_='h4-like')
            if h2 and 'taux de cotisations employeur' in h2.get_text(strip=True).lower():
                employeur_section = article
                break
        if not employeur_section:
            return None

        # Ligne "Cotisation AGS"
        value_text = ""
        for row in employeur_section.find_all('tr', class_='table_custom__tbody'):
            th = row.find('th')
            if th and 'Cotisation AGS' in th.get_text(strip=True):
                td = row.find('td')
                if td:
                    value_text = td.get_text(" ", strip=True)
                break
        if not value_text:
            return None

        return _extract_rate_from_value_text(value_text, is_ett=is_ett)

    except Exception:
        return None


def make_payload(taux: float | None) -> dict:
    return {
        "id": "ags",
        "type": "cotisation",
        "libelle": "Cotisation AGS",
        "base": "brut",
        "valeurs": {"salarial": None, "patronal": taux},
        "meta": {
            "source": [{"url": URL_URSSAF, "label": "URSSAF", "date_doc": ""}],
            "generator": "scripts/AGS/AGS.py",
        },
    }


if __name__ == "__main__":
    # Lit le flag ETT dans la config entreprise (si présent)
    is_ett = False
    try:
        with open(FICHIER_ENTREPRISE, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        is_ett = bool(
            cfg["PARAMETRES_ENTREPRISE"]["conditions_cotisations"].get(
                "est_entreprise_travail_temporaire", False
            )
        )
    except Exception:
        pass

    taux = get_taux_ags(is_ett=is_ett)
    print(json.dumps(make_payload(taux), ensure_ascii=False))
