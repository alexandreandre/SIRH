# scripts/PSS/PSS_LegiSocial.py

import json
import re
import sys
import time
from datetime import datetime, timezone

from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service as ChromeService
from webdriver_manager.chrome import ChromeDriverManager

URL_LEGISOCIAL = "https://www.legisocial.fr/reperes-sociaux/plafond-securite-sociale-2025.html"

# --- UTILITAIRES ---

def iso_now() -> str:
    """Retourne la date et l'heure actuelles au format ISO 8601 UTC."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def parse_valeur_numerique(text: str) -> int:
    """Nettoie un texte (ex: "47.100 €"), le convertit en entier."""
    if not text: return 0
    cleaned_text = text.replace('.', '').replace('€', '').replace('\xa0', '').replace(' ', '').strip()
    return int(cleaned_text)

# --- SCRAPER ---

def get_plafonds_ss_legisocial() -> dict | None:
    """Scrape le site LegiSocial en utilisant Selenium pour plus de fiabilité."""
    driver = None
    try:
        print("Initialisation du navigateur Selenium en mode invisible...", file=sys.stderr)
        chrome_options = Options()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.0.0 Safari/537.36")
        
        driver = webdriver.Chrome(service=ChromeService(ChromeDriverManager().install()), options=chrome_options)
        
        print(f"Navigation vers l'URL : {URL_LEGISOCIAL}...", file=sys.stderr)
        driver.get(URL_LEGISOCIAL)
        time.sleep(3) # Laisse le temps à la page (et aux éventuels scripts) de se charger

        print("Récupération du code HTML final...", file=sys.stderr)
        page_html = driver.page_source
        soup = BeautifulSoup(page_html, "html.parser")

        table = soup.find('table', {'border': '1'})
        if not table:
            # Fallback si l'attribut border change
            table = soup.find('th', string=re.compile(r'Plafond annuel')).find_parent('table')

        if not table:
            raise ValueError("Table des plafonds introuvable sur la page.")

        plafonds = {}
        # Note: LegiSocial ne liste pas toujours les plafonds quinzaine/hebdomadaire
        key_mapping = {
            'annuel': 'annuel', 'trimestriel': 'trimestriel', 'mensuel': 'mensuel',
            'jour': 'journalier', 'heure': 'horaire'
        }
        
        for row in table.find_all('tr'):
            label_cell = row.find(['th', 'td'])
            if not label_cell: continue

            libelle = label_cell.get_text().lower()
            value_cell = label_cell.find_next_sibling(['th', 'td'])

            if value_cell:
                for keyword, key in key_mapping.items():
                    if keyword in libelle:
                        valeur = parse_valeur_numerique(value_cell.get_text())
                        plafonds[key] = valeur
                        print(f"  - Plafond '{key}' trouvé : {valeur} €", file=sys.stderr)
                        break
        
        if len(plafonds) < 5:
             raise ValueError(f"Tous les plafonds principaux n'ont pas été trouvés. Requis: 5, Trouvés: {len(plafonds)}")
        
        return plafonds

    except Exception as e:
        print(f"ERREUR : Le scraping a échoué. Raison : {e}", file=sys.stderr)
        return None
    finally:
        if driver:
            print("Fermeture du navigateur Selenium.", file=sys.stderr)
            driver.quit()

# --- FONCTION PRINCIPALE ---
def main():
    """Orchestre le scraping et génère la sortie JSON pour l'orchestrateur."""
    plafonds_data = get_plafonds_ss_legisocial()
    
    if not plafonds_data:
        print("ERREUR CRITIQUE: Le scraping des plafonds via LegiSocial a échoué.", file=sys.stderr)
        sys.exit(1)

    payload = {
        "id": "plafonds_securite_sociale",
        "type": "bareme_plafond",
        "libelle": "Plafonds de la Sécurité Sociale",
        "sections": plafonds_data,
        "meta": {
            "source": [{
                "url": URL_LEGISOCIAL,
                "label": "LegiSocial - Plafond de la Sécurité Sociale",
                "date_doc": ""
            }],
            "scraped_at": iso_now(),
            "generator": "scripts/PSS/PSS_LegiSocial.py",
            "method": "secondary"
        }
    }
    
    # Impression du JSON final sur la sortie standard
    print(json.dumps(payload, ensure_ascii=False))

if __name__ == "__main__":
    main()