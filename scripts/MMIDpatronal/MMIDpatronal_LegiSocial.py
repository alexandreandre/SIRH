# scripts/MMIDpatronal/MMIDpatronal_LegiSocial.py
import json
import re
from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup

URL_LEGISOCIAL = "https://www.legisocial.fr/reperes-sociaux/taux-cotisations-sociales-urssaf-2025.html"

def iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def parse_taux(text: str) -> float | None:
    if not text:
        return None
    try:
        cleaned_text = text.replace(",", ".").replace("%", "").strip()
        m = re.search(r"([0-9]+\.?[0-9]*)", cleaned_text)
        if not m:
            return None
        return round(float(m.group(1)) / 100.0, 5)
    except Exception:
        return None

def get_taux_maladie_legisocial() -> dict | None:
    try:
        r = requests.get(
            URL_LEGISOCIAL,
            timeout=20,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.0.0 Safari/537.36"},
        )
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")

        table_title = soup.find(lambda tag: tag.name in ["h2", "h3"] and "Quels sont les taux de cotisations en 2025" in tag.get_text())
        if not table_title:
            raise ValueError("Titre de la table 2025 introuvable.")
        table = table_title.find_next("table")
        if not table:
            raise ValueError("Table des cotisations introuvable.")

        taux_trouves: dict[str, float] = {}
        for row in table.find("tbody").find_all("tr"):
            cells = row.find_all("td")
            if len(cells) > 4:
                libelle = cells[0].get_text().lower()
                if "maladie" in libelle and "alsace-moselle" not in libelle:
                    taux_text = cells[4].get_text()
                    taux = parse_taux(taux_text)
                    if taux is None:
                        continue
                    if "≤" in libelle or "<" in libelle:
                        taux_trouves["reduit"] = taux
                    elif ">" in libelle:
                        taux_trouves["plein"] = taux

        if "reduit" in taux_trouves or "plein" in taux_trouves:
            return taux_trouves
        return None
    except Exception:
        return None

def build_payload(rate_plein: float | None, rate_reduit: float | None) -> dict:
    return {
        "id": "securite_sociale_maladie",
        "type": "cotisation",
        "libelle": "Sécurité sociale - Maladie, Maternité, Invalidité, Décès",
        "base": "brut",
        "valeurs": {
            "salarial": None,
            "patronal_plein": rate_plein,
            "patronal_reduit": rate_reduit,
        },
        "meta": {
            "source": [{"url": URL_LEGISOCIAL, "label": "LégiSocial — Taux cotisations URSSAF 2025", "date_doc": ""}],
            "scraped_at": iso_now(),
            "generator": "scripts/MMIDpatronal/MMIDpatronal_LegiSocial.py",
            "method": "secondary",
        },
    }

def main() -> None:
    rates = get_taux_maladie_legisocial() or {}
    payload = build_payload(rates.get("plein"), rates.get("reduit"))
    print(json.dumps(payload, ensure_ascii=False))

if __name__ == "__main__":
    main()
