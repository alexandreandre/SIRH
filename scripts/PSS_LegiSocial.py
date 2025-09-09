# scripts/PSS_LegiSocial.py

import json
import re
import time
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.options import Options

# --- Fichiers et URL cibles ---
FICHIER_ENTREPRISE = 'config/parametres_entreprise.json'
URL_LEGISOCIAL = "https://www.legisocial.fr/reperes-sociaux/plafond-securite-sociale-2025.html"

def parse_valeur_numerique(text: str) -> int:
    """Nettoie un texte (ex: "47.100 €"), le convertit en entier."""
    if not text: return 0
    cleaned_text = text.replace('.', '').replace('€', '').replace('\xa0', '').replace(' ', '').strip()
    return int(cleaned_text)

def get_plafonds_ss_legisocial() -> dict | None:
    """Scrape le site LegiSocial en utilisant Selenium pour plus de fiabilité."""
    driver = None
    try:
        print("Initialisation du navigateur Selenium en mode invisible...")
        chrome_options = Options()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.0.0 Safari/537.36")
        driver = webdriver.Chrome(service=ChromeService(ChromeDriverManager().install()), options=chrome_options)
        
        print(f"Navigation vers l'URL : {URL_LEGISOCIAL}...")
        driver.get(URL_LEGISOCIAL)
        time.sleep(3)

        print("Récupération du code HTML final...")
        page_html = driver.page_source
        soup = BeautifulSoup(page_html, "html.parser")

        table = soup.find('table', {'border': '1'})
        if not table:
            # Fallback si l'attribut border change
            table = soup.find('th', string=re.compile(r'Plafond annuel')).find_parent('table')

        if not table:
            raise ValueError("Table des plafonds introuvable sur la page.")

        plafonds = {}
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
                        print(f"  - Plafond '{key}' trouvé : {valeur} €")
                        break
        
        if len(plafonds) < 5:
             raise ValueError(f"Tous les plafonds principaux n'ont pas été trouvés. Trouvés : {plafonds.keys()}")
        
        return plafonds

    except Exception as e:
        print(f"ERREUR : Le scraping a échoué. Raison : {e}")
        return None
    finally:
        if driver:
            print("Fermeture du navigateur Selenium.")
            driver.quit()

def update_config_file(nouveaux_plafonds: dict):
    """Met à jour le fichier parametres_entreprise.json."""
    try:
        with open(FICHIER_ENTREPRISE, 'r', encoding='utf-8') as f:
            config = json.load(f)
        
        constantes = config['PARAMETRES_ENTREPRISE']['constantes_paie_2025']
        
        updated_data = constantes.get('plafonds_securite_sociale', {})
        updated_data.update(nouveaux_plafonds)

        print("\nMise à jour de l'objet des plafonds de la Sécurité Sociale...")
        constantes['plafonds_securite_sociale'] = updated_data
        
        with open(FICHIER_ENTREPRISE, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
            
        print(f"✅ Le fichier '{FICHIER_ENTREPRISE}' a été mis à jour avec succès.")
        
    except Exception as e:
        print(f"ERREUR : Une erreur est survenue lors de la mise à jour : {e}")

if __name__ == "__main__":
    valeurs_plafonds = get_plafonds_ss_legisocial()
    
    if valeurs_plafonds:
        update_config_file(valeurs_plafonds)