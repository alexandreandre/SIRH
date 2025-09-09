# scripts/alloc/alloc.py

import json
import os
import re
import sys
import requests
from bs4 import BeautifulSoup
from typing import Optional, Tuple, Dict, Any

URL_URSSAF = "https://www.urssaf.fr/accueil/outils-documentation/taux-baremes/taux-cotisations-secteur-prive.html"


def _to_rate(num_str: str) -> Optional[float]:
    """'3,45' or '3.45' -> 0.0345"""
    try:
        return round(float(num_str.replace(',', '.')) / 100.0, 6)
    except Exception:
        return None


def _extract_rates_from_text(text: str) -> Tuple[Optional[float], Optional[float]]:
    """
    Tente d'extraire 'taux plein' et 'taux réduit' depuis un bloc de texte.
    Si les libellés ne sont pas présents, prend max=plein, min=réduit parmi les % trouvés.
    """
    # 1) motifs explicites
    m_plein = re.search(r"[Tt]aux\s+plein\s*(?:[:à=])?\s*([0-9]+(?:[.,][0-9]+)?)\s*%", text)
    m_reduit = re.search(r"[Tt]aux\s+r[ée]duit\s*(?:[:à=])?\s*([0-9]+(?:[.,][0-9]+)?)\s*%", text)

    plein = _to_rate(m_plein.group(1)) if m_plein else None
    reduit = _to_rate(m_reduit.group(1)) if m_reduit else None

    # 2) fallback : prendre les 2 % du bloc et les ordonner
    if plein is None or reduit is None:
        all_percents = re.findall(r"([0-9]+(?:[.,][0-9]+)?)\s*%", text)
        # garde uniquement des nombres plausibles (0..100)
        vals = []
        for s in all_percents:
            try:
                v = float(s.replace(',', '.'))
                if 0 <= v <= 100:
                    vals.append(v)
            except Exception:
                pass
        vals = sorted(set(vals))  # unique + tri
        if len(vals) >= 2:
            # plus grand = plein, plus petit = réduit
            reduit = _to_rate(str(vals[0])) if reduit is None else reduit
            plein = _to_rate(str(vals[-1])) if plein is None else plein

    return plein, reduit


def get_allocations_rates() -> Tuple[Optional[float], Optional[float]]:
    """
    Scrape l'URSSAF et retourne (taux_plein, taux_reduit) en taux réels (ex: 0.0345).
    """
    try:
        print(f"[alloc] scraping: {URL_URSSAF}", file=sys.stderr)
        r = requests.get(URL_URSSAF, timeout=25, headers={
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
        })
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")

        # Trouver la section "Taux de cotisations employeur"
        employeur_section = None
        for article in soup.find_all('article'):
            h2 = article.find('h2', class_='h4-like')
            if h2 and 'taux de cotisations employeur' in h2.get_text(strip=True).lower():
                employeur_section = article
                break

        if not employeur_section:
            raise RuntimeError("Section 'Taux de cotisations employeur' introuvable.")

        # Trouver la ligne Allocations familiales
        row_text = ""
        for row in employeur_section.find_all('tr'):
            th = row.find('th')
            if th and 'allocations familiales' in th.get_text(" ", strip=True).lower():
                # concatène l'ensemble de la ligne pour capter toutes les variantes d’affichage
                row_text = row.get_text(" ", strip=True)
                break

        if not row_text:
            # fallback : utiliser tout le texte de la section employeur et laisser le parser trouver
            row_text = employeur_section.get_text(" ", strip=True)

        plein, reduit = _extract_rates_from_text(row_text)
        print(f"[alloc] parsed: plein={plein} reduit={reduit}", file=sys.stderr)
        return plein, reduit

    except Exception as e:
        print(f"[alloc][ERREUR] {e}", file=sys.stderr)
        return None, None


def payload(plein: Optional[float], reduit: Optional[float]) -> Dict[str, Any]:
    return {
        "id": "allocations_familiales",
        "type": "cotisation",
        "libelle": "Allocations familiales",
        "base": "brut",
        "valeurs": {
            "salarial": None,
            "patronal_plein": plein,
            "patronal_reduit": reduit,
        },
        "meta": {
            "source": [
                {
                    "url": URL_URSSAF,
                    "label": "URSSAF - Taux de cotisations employeur",
                    "date_doc": ""
                }
            ],
            "generator": "scripts/alloc/alloc.py"
        }
    }


if __name__ == "__main__":
    plein, reduit = get_allocations_rates()
    print(json.dumps(payload(plein, reduit), ensure_ascii=False))
