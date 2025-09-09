# scripts/FNAL/FNAL_LegiSocial.py
import json
import os
import re
import sys
from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup

URL_LEGISOCIAL = "https://www.legisocial.fr/reperes-sociaux/taux-cotisations-sociales-urssaf-2025.html"

def iso_now() -> str:
    """Retourne la date et l'heure actuelles au format ISO 8601 UTC."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def _parse_percent_to_rate(text: str) -> float | None:
    """Extrait un pourcentage d'une chaîne et le convertit en taux décimal."""
    if not text:
        return None
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*%", text)
    if not m:
        return None
    return round(float(m.group(1).replace(",", ".")) / 100.0, 6)

def _fetch_page(url: str) -> BeautifulSoup:
    """Récupère et parse le contenu HTML d'une URL."""
    r = requests.get(
        url,
        timeout=25,
        headers={
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
        },
    )
    r.raise_for_status()
    return BeautifulSoup(r.text, "html.parser")

def scrape_fnal_rates_legisocial() -> dict[str, float | None]:
    """
    Scrape et retourne les deux taux FNAL depuis LegiSocial.
    """
    print(f"Scraping de l'URL : {URL_LEGISOCIAL}...", file=sys.stderr)
    try:
        soup = _fetch_page(URL_LEGISOCIAL)
        taux_moins_50, taux_50_et_plus = None, None

        # Expressions régulières pour trouver les bonnes lignes
        pat_row = re.compile(r"fnal", re.IGNORECASE)
        pat_moins_50 = re.compile(r"moins\s+de\s+50", re.IGNORECASE)
        pat_50_et_plus = re.compile(r"(50\s+salari[ée]s\s+et\s+plus|au\s+moins\s+50)", re.IGNORECASE)

        # La structure de la table peut varier, on cherche la bonne
        table_title = soup.find(lambda tag: tag.name in ['h2', 'h3'] and 'Quels sont les taux de cotisations en 2025' in tag.get_text())
        if not table_title:
            raise ValueError("Titre de la table des cotisations introuvable.")
        table = table_title.find_next('table')
        if not table:
            raise ValueError("Table des cotisations introuvable après le titre.")

        for tr in table.find_all("tr"):
            cells = tr.find_all(["th", "td"])
            if len(cells) < 2: continue
            
            label = cells[0].get_text(" ", strip=True)
            if not pat_row.search(label): continue
            
            # Le taux patronal est généralement dans la dernière cellule
            rate = _parse_percent_to_rate(cells[-1].get_text(" ", strip=True))
            if rate is None: continue

            if pat_moins_50.search(label):
                taux_moins_50 = rate
            elif pat_50_et_plus.search(label):
                taux_50_et_plus = rate
        
        print(f"  - Taux FNAL (< 50 salariés) trouvé : {taux_moins_50}", file=sys.stderr)
        print(f"  - Taux FNAL (50+ salariés) trouvé : {taux_50_et_plus}", file=sys.stderr)

        return {"patronal_moins_50": taux_moins_50, "patronal_50_et_plus": taux_50_et_plus}
    except Exception as e:
        print(f"ERREUR : Le scraping a échoué. Raison : {e}", file=sys.stderr)
        return {"patronal_moins_50": None, "patronal_50_et_plus": None}

def main() -> None:
    """
    Orchestre le scraping et génère la sortie JSON pour l'orchestrateur.
    """
    rates = scrape_fnal_rates_legisocial()

    if rates.get("patronal_moins_50") is None or rates.get("patronal_50_et_plus") is None:
        print("ERREUR CRITIQUE: Un ou plusieurs taux FNAL n'ont pas pu être scrapés depuis LegiSocial.", file=sys.stderr)
        sys.exit(1)

    payload = {
        "id": "fnal",
        "type": "cotisation",
        "libelle": "Fonds National d’Aide au Logement (FNAL)",
        "sections": {
            "salarial": None,
            "patronal_moins_50": rates["patronal_moins_50"],
            "patronal_50_et_plus": rates["patronal_50_et_plus"]
        },
        "meta": {
            "source": [{"url": URL_LEGISOCIAL, "label": "LégiSocial — Taux cotisations URSSAF", "date_doc": ""}],
            "scraped_at": iso_now(),
            "generator": "scripts/FNAL/FNAL_LegiSocial.py",
            "method": "secondary",
        },
    }
    
    # Sortie JSON stricte pour l'orchestrateur
    print(json.dumps(payload, ensure_ascii=False))

if __name__ == "__main__":
    main()