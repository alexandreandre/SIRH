# scripts/vieillessepatronal/vieillessepatronal_LegiSocial.py

import json
import re
import sys
from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup

URL_LEGISOCIAL = "https://www.legisocial.fr/reperes-sociaux/taux-cotisations-sociales-urssaf-2025.html"

# --- UTILITAIRES ---
def iso_now() -> str:
    """Retourne la date et l'heure actuelles au format ISO 8601 UTC."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def parse_taux(text: str) -> float | None:
    """Nettoie et convertit un texte en taux réel (ex: "8,55 %" -> 0.0855)."""
    if not text:
        return None
    try:
        cleaned_text = text.replace(',', '.').replace('%', '').strip()
        numeric_part = re.search(r"([0-9]+\.?[0-9]*)", cleaned_text)
        if not numeric_part:
            return None
        taux = float(numeric_part.group(1)) / 100.0
        return round(taux, 5)
    except (ValueError, AttributeError):
        return None

# --- SCRAPER ---
def get_taux_vieillesse_patronal_legisocial() -> dict | None:
    """Scrape LegiSocial pour trouver les taux de l'assurance vieillesse patronale."""
    try:
        print(f"Scraping de l'URL : {URL_LEGISOCIAL}...", file=sys.stderr)
        response = requests.get(URL_LEGISOCIAL, timeout=20, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/5.36 (KHTML, like Gecko) Chrome/108.0.0.0 Safari/537.36"
        })
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        
        table_title = soup.find(lambda tag: tag.name in ['h2', 'h3'] and 'Quels sont les taux de cotisations en 2025' in tag.get_text())
        if not table_title:
            raise ValueError("Titre de la table des cotisations introuvable.")
        table = table_title.find_next('table')
        if not table:
            raise ValueError("Table des cotisations introuvable après le titre.")

        taux_trouves = {}
        for row in table.find('tbody').find_all('tr'):
            cells = row.find_all('td')
            if len(cells) > 4:
                libelle = cells[0].get_text(strip=True).lower()
                
                # Le taux patronal est dans la 5ème colonne (index 4)
                if "vieillesse déplafonnée" in libelle:
                    taux = parse_taux(cells[4].get_text())
                    if taux is not None:
                        print(f"  - Taux Vieillesse Déplafonnée (patronal) trouvé : {taux*100:.2f}%", file=sys.stderr)
                        taux_trouves['deplafonne'] = taux

                elif "vieillesse plafonnée" in libelle:
                    taux = parse_taux(cells[4].get_text())
                    if taux is not None:
                        print(f"  - Taux Vieillesse Plafonnée (patronal) trouvé : {taux*100:.2f}%", file=sys.stderr)
                        taux_trouves['plafonne'] = taux

        if "deplafonne" in taux_trouves and "plafonne" in taux_trouves:
            return taux_trouves
        else:
            raise ValueError("Impossible de trouver les deux taux de vieillesse (plafonné et déplafonné).")

    except Exception as e:
        print(f"ERREUR : Le scraping a échoué. Raison : {e}", file=sys.stderr)
        return None

# --- FONCTION PRINCIPALE ---
def main():
    """Orchestre le scraping et génère la sortie JSON pour l'orchestrateur."""
    taux_data = get_taux_vieillesse_patronal_legisocial()
    
    if not taux_data:
        print("ERREUR CRITIQUE: Le scraping des taux via LegiSocial a échoué.", file=sys.stderr)
        sys.exit(1)

    payload = {
        "id": "assurance_vieillesse_patronal",
        "type": "taux_cotisation",
        "libelle": "Taux de cotisation patronale - Assurance Vieillesse",
        "sections": taux_data,
        "meta": {
            "source": [{
                "url": URL_LEGISOCIAL,
                "label": "LegiSocial - Taux de cotisations sociales",
                "date_doc": ""
            }],
            "scraped_at": iso_now(),
            "generator": "scripts/vieillessepatronal/vieillessepatronal_LegiSocial.py",
            "method": "secondary"
        }
    }
    
    print(json.dumps(payload, ensure_ascii=False))

if __name__ == "__main__":
    main()