# scripts/CSA/CSA.py

import json
import re
import sys
from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup

URL_URSSAF = "https://www.urssaf.fr/accueil/outils-documentation/taux-baremes/taux-cotisations-secteur-prive.html"


def iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_percent_to_rate(text: str) -> float | None:
    if not text:
        return None
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*%", text)
    if not m:
        return None
    return round(float(m.group(1).replace(",", ".")) / 100.0, 6)


def get_taux_csa() -> float | None:
    """
    Scrape le site de l'URSSAF pour trouver le taux patronal CSA.
    """
    try:
        r = requests.get(
            URL_URSSAF,
            timeout=25,
            headers={
                "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "fr-FR,fr;q=0.9",
            },
        )
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")

        # 1) Trouver la section "Taux de cotisations employeur"
        employeur_section = None
        for article in soup.find_all("article"):
            h2 = article.find("h2", class_="h4-like")
            if h2 and "taux de cotisations employeur" in h2.get_text(strip=True).lower():
                employeur_section = article
                break
        if not employeur_section:
            raise ValueError("Section 'Taux de cotisations employeur' introuvable.")

        # 2) Parcourir les lignes du tableau pour "Contribution solidarité autonomie (CSA)"
        for row in employeur_section.find_all("tr", class_="table_custom__tbody"):
            header_cell = row.find("th")
            if header_cell and "Contribution solidarité autonomie (CSA)" in header_cell.get_text(strip=True):
                value_cell = row.find("td")
                if not value_cell:
                    raise ValueError("Ligne 'CSA' trouvée, mais cellule de valeur manquante.")
                taux = parse_percent_to_rate(value_cell.get_text(strip=True))
                if taux is None:
                    raise ValueError(f"Taux CSA introuvable dans la cellule: '{value_cell.get_text(strip=True)}'")
                return taux

        raise ValueError("Ligne 'Contribution solidarité autonomie (CSA)' introuvable.")
    except Exception:
        return None


def build_payload(rate_patronal: float | None) -> dict:
    return {
        "id": "csa",
        "type": "cotisation",
        "libelle": "Contribution Solidarité Autonomie (CSA)",
        "base": "brut",
        "valeurs": {"salarial": None, "patronal": rate_patronal},
        "meta": {
            "source": [{"url": URL_URSSAF, "label": "URSSAF — Taux secteur privé", "date_doc": ""}],
            "scraped_at": iso_now(),
            "generator": "CSA/CSA.py",
            "method": "primary",
        },
    }


if __name__ == "__main__":
    taux = get_taux_csa()
    payload = build_payload(taux)
    # L’orchestrateur consomme le JSON via stdout
    print(json.dumps(payload, ensure_ascii=False))
    # Pas de mise à jour de fichier ici: orchestrateur gère l’écriture.
