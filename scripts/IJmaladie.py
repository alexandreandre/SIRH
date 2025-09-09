# scripts/IJmaladie.py

import json
import re
import time
from bs4 import BeautifulSoup

# Imports pour Selenium
from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.options import Options

# --- Fichiers et URL cibles ---
FICHIER_BAREMES = 'config/baremes.json'
URL_AMELI = "https://www.ameli.fr/entreprise/vos-salaries/montants-reference/indemnites-journalieres-montants-maximum"

def parse_valeur_numerique(text: str) -> float:
    """Nettoie et convertit un texte en nombre (float)."""
    if not text: return 0.0
    cleaned = text.replace('€', '').replace('\xa0', '').replace('\u202f', '').replace(' ', '').replace(',', '.')
    match = re.search(r"([0-9]+\.?[0-9]*)", cleaned)
    return float(match.group(1)) if match else 0.0

def get_all_plafonds_ij() -> dict | None:
    """
    Scrape le site ameli.fr en chargeant la page avec Selenium, puis en analysant
    directement les lignes de tableau avec BeautifulSoup.
    """
    driver = None
    try:
        # --- 1. Récupération du HTML avec Selenium ---
        print("Initialisation du navigateur Selenium en mode invisible...")
        chrome_options = Options()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.0.0 Safari/537.36")
        driver = webdriver.Chrome(service=ChromeService(ChromeDriverManager().install()), options=chrome_options)
        
        print(f"Navigation vers l'URL et attente de 5 secondes...")
        driver.get(URL_AMELI)
        time.sleep(5) 

        print("Récupération du code HTML final...")
        page_html = driver.page_source
        soup = BeautifulSoup(page_html, "html.parser")

        # --- 2. Parsing direct et robuste ---
        print("Analyse de toutes les lignes de tableau de la page...")
        plafonds = {}
        all_rows = soup.find_all('tr')
        
        for row in all_rows:
            cells = row.find_all('td')
            if len(cells) == 2:
                libelle = cells[0].get_text().lower()
                valeur_text = cells[1].get_text()
                
                # On identifie les lignes par des mots-clés uniques
                if "29e jour" in libelle:
                    plafonds['at_mp_majoree'] = parse_valeur_numerique(valeur_text)
                elif "accident du travail" in libelle:
                    plafonds['at_mp'] = parse_valeur_numerique(valeur_text)
                elif "maternité" in libelle:
                    plafonds['maternite_paternite'] = parse_valeur_numerique(valeur_text)
                elif "arrêt maladie" in libelle:
                    plafonds['maladie'] = parse_valeur_numerique(valeur_text)

        print(f"Plafonds extraits : {plafonds}")

        if len(plafonds) != 4:
            with open('debug_ameli.html', 'w', encoding='utf-8') as f:
                f.write(page_html)
            raise ValueError(f"Toutes les indemnités n'ont pas été trouvées. Trouvées : {len(plafonds)} sur 4. Fichier 'debug_ameli.html' créé.")
        
        return plafonds

    except Exception as e:
        print(f"ERREUR : Le scraping a échoué. Raison : {e}")
        return None
    finally:
        if driver:
            print("Fermeture du navigateur Selenium.")
            driver.quit()

def update_config_file(nouveaux_plafonds: dict):
    # Cette fonction ne change pas
    try:
        with open(FICHIER_BAREMES, 'r', encoding='utf-8') as f:
            config = json.load(f)
        
        ij_config = config.setdefault('SECURITE_SOCIALE_2025', {}).setdefault('plafonds_indemnites_journalieres', {})
        
        if 'indemnites_journalieres_maladie' in config['SECURITE_SOCIALE_2025']:
            del config['SECURITE_SOCIALE_2025']['indemnites_journalieres_maladie']

        print("\nMise à jour du fichier de configuration...")
        ij_config.update(nouveaux_plafonds)
        
        with open(FICHIER_BAREMES, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
            
        print(f"✅ Le fichier '{FICHIER_BAREMES}' a été mis à jour avec succès.")
        
    except Exception as e:
        print(f"\nERREUR : Une erreur est survenue lors de la mise à jour : {e}")


if __name__ == "__main__":
    valeurs = get_all_plafonds_ij()
    
    if valeurs is not None:
        update_config_file(valeurs)