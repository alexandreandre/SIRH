# scripts/MMIDsalarial/MMIDsalarial_LegiSocial.py

import json
import re
import sys
from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup

URL_LEGISOCIAL = "https://www.legisocial.fr/reperes-sociaux/taux-cotisations-sociales-urssaf-2025.html"

# --- FONCTIONS UTILITAIRES ---

def iso_now() -> str:
    """Retourne la date et l'heure actuelles au format ISO 8601 UTC."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def parse_taux(text: str) -> float | None:
    """
    Nettoie un texte (ex: "1,30 %"), le convertit en float (1.30)
    puis en taux réel (0.0130).
    """
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

# --- FONCTION DE SCRAPING ---

def get_taux_alsace_moselle_legisocial() -> float | None:
    """
    Scrape le site LegiSocial pour trouver le taux salarial maladie du régime Alsace-Moselle.
    """
    try:
        print(f"Scraping de l'URL : {URL_LEGISOCIAL}...", file=sys.stderr)
        response = requests.get(URL_LEGISOCIAL, timeout=20, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.0.0 Safari/537.36"
        })
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")
        
        table_title = soup.find(lambda tag: tag.name in ['h2', 'h3'] and 'Quels sont les taux de cotisations en 2025' in tag.get_text())
        if not table_title:
            raise ValueError("Titre de la table principale des cotisations 2025 introuvable.")
            
        table = table_title.find_next('table')
        if not table:
            raise ValueError("Table des cotisations introuvable après le titre.")

        for row in table.find('tbody').find_all('tr'):
            cells = row.find_all('td')
            if len(cells) > 3:
                libelle = cells[0].get_text().lower()
                if "maladie" in libelle and "alsace-moselle" in libelle:
                    # Le taux salarial est dans la 4ème colonne (index 3)
                    taux_text = cells[3].get_text()
                    taux = parse_taux(taux_text)
                    
                    if taux is not None:
                        print(f"Taux salarial maladie (Alsace-Moselle) trouvé : {taux*100:.2f}%", file=sys.stderr)
                        return taux
        
        raise ValueError("Ligne correspondant au régime Alsace-Moselle introuvable.")

    except Exception as e:
        print(f"ERREUR : Le scraping a échoué. Raison : {e}", file=sys.stderr)
        return None

# --- FONCTION PRINCIPALE ---

def main():
    """
    Orchestre le scraping et génère la sortie JSON pour l'orchestrateur.
    """
    taux = get_taux_alsace_moselle_legisocial()

    if taux is None:
        print("ERREUR CRITIQUE: Le taux n'a pas pu être récupéré.", file=sys.stderr)
        sys.exit(1)

    # Assemblage du payload final, identique en structure au script principal
    payload = {
        "id": "maladie_alsace_moselle",
        "type": "taux_cotisation_specifique",
        "libelle": "Taux de cotisation salariale maladie - Alsace-Moselle",
        "sections": {
            "alsace_moselle": {
                "taux_salarial": taux
            }
        },
        "meta": {
            "source": [{
                "url": URL_LEGISOCIAL,
                "label": "LegiSocial - Taux de cotisations sociales",
                "date_doc": ""
            }],
            "scraped_at": iso_now(),
            "generator": "scripts/MMIDsalarial/MMIDsalarial_LegiSocial.py",
            "method": "secondary"
        }
    }

    # Impression du JSON final sur la sortie standard
    print(json.dumps(payload, ensure_ascii=False))


if __name__ == "__main__":
    main()