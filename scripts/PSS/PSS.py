# scripts/PSS/PSS.py

import json
import re
import sys
from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup

URL_URSSAF = "https://www.urssaf.fr/accueil/outils-documentation/taux-baremes/plafonds-securite-sociale.html"

# --- UTILITAIRES ---

def iso_now() -> str:
    """Retourne la date et l'heure actuelles au format ISO 8601 UTC."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def parse_valeur_numerique(text: str) -> int:
    """Nettoie et convertit un texte contenant un montant en entier."""
    if not text: return 0
    cleaned_text = text.replace('\xa0', '').replace(' ', '').replace('€', '').strip()
    return int(cleaned_text)

# --- SCRAPER ---

def get_plafonds_ss() -> dict | None:
    """
    Scrape le site de l'URSSAF pour récupérer l'ensemble des plafonds de la SS.
    """
    try:
        print(f"Scraping de l'URL : {URL_URSSAF}...", file=sys.stderr)
        r = requests.get(URL_URSSAF, timeout=20, headers={
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
        })
        r.raise_for_status()

        soup = BeautifulSoup(r.text, "html.parser")
        
        main_section = soup.find('div', id='metropole-outre-mer')
        if not main_section:
            raise ValueError("Section principale des plafonds (ID: metropole-outre-mer) introuvable.")

        key_mapping = {
            'Année': 'annuel',
            'Trimestre': 'trimestriel',
            'Mois': 'mensuel',
            'Quinzaine': 'quinzaine',
            'Semaine': 'hebdomadaire',
            'Jour': 'journalier',
            'Heure': 'horaire'
        }
        
        plafonds = {}
        table_rows = main_section.find_all('tr', class_='table_custom__tbody')
        
        for row in table_rows:
            header_cell = row.find('th')
            value_cell = row.find('td')
            
            if header_cell and value_cell:
                libelle = header_cell.get_text(strip=True)
                if libelle in key_mapping:
                    json_key = key_mapping[libelle]
                    valeur = parse_valeur_numerique(value_cell.get_text())
                    plafonds[json_key] = valeur
                    print(f"  - Plafond '{libelle}' trouvé : {valeur} €", file=sys.stderr)

        if len(plafonds) != len(key_mapping):
            print(f"AVERTISSEMENT : Tous les plafonds n'ont pas été trouvés. Attendu: {len(key_mapping)}, Trouvé: {len(plafonds)}", file=sys.stderr)
            
        return plafonds

    except Exception as e:
        print(f"ERREUR : Le scraping a échoué. Raison : {e}", file=sys.stderr)
        return None

# --- FONCTION PRINCIPALE ---

def main():
    """Orchestre le scraping et génère la sortie JSON pour l'orchestrateur."""
    plafonds_data = get_plafonds_ss()
    
    if not plafonds_data:
        print("ERREUR CRITIQUE: Le scraping des plafonds de la SS a échoué ou n'a retourné aucune donnée.", file=sys.stderr)
        sys.exit(1)

    payload = {
        "id": "plafonds_securite_sociale",
        "type": "bareme_plafond",
        "libelle": "Plafonds de la Sécurité Sociale",
        "sections": plafonds_data,
        "meta": {
            "source": [{
                "url": URL_URSSAF,
                "label": "URSSAF - Plafonds de la Sécurité Sociale",
                "date_doc": ""
            }],
            "scraped_at": iso_now(),
            "generator": "scripts/PSS/PSS.py",
            "method": "primary"
        }
    }
    
    # Impression du JSON final sur la sortie standard
    print(json.dumps(payload, ensure_ascii=False))

if __name__ == "__main__":
    main()