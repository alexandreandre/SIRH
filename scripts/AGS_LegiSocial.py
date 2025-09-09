# scripts/AGS_LegiSocial.py 

import json
import re
import time
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.options import Options

# --- Fichiers et URL cibles ---
FICHIER_TAUX = 'config/taux_cotisations.json'
URL_LEGISOCIAL = "https://www.legisocial.fr/reperes-sociaux/taux-cotisations-sociales-urssaf-2025.html"

def parse_taux(text: str) -> float | None:
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

def get_taux_ags_legisocial() -> float | None:
    driver = None
    try:
        print("Initialisation du navigateur Selenium en mode invisible...")
        chrome_options = Options()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.0.0 Safari/537.36")

        driver = webdriver.Chrome(service=ChromeService(ChromeDriverManager().install()), options=chrome_options)
        
        print(f"Navigation vers l'URL : {URL_LEGISOCIAL}...")
        driver.get(URL_LEGISOCIAL)
        time.sleep(3) 

        print("Récupération du code HTML final de la page...")
        page_html = driver.page_source
        soup = BeautifulSoup(page_html, "html.parser")
        
        all_headers = soup.find_all('h3')
        chomage_header = None
        for header in all_headers:
            if 'Cotisations chômage' in header.get_text():
                chomage_header = header
                print("Titre de la section 'Cotisations chômage' trouvé !")
                break 
        
        if not chomage_header:
            raise ValueError("Titre 'Cotisations chômage' introuvable.")
        
        table = chomage_header.find_next('table')
        if not table:
            raise ValueError("Table des cotisations chômage introuvable après le titre.")

        # --- LOGIQUE DE PARSING SIMPLIFIÉE ET CORRIGÉE ---
        # On parcourt les lignes pour trouver celle qui contient "AGS"
        taux_ags = None
        for row in table.find('tbody').find_all('tr'):
            cells = row.find_all('td')
            # On cherche simplement la ligne dont le premier champ contient "AGS"
            if len(cells) > 4 and "AGS" in cells[0].get_text():
                print("Ligne 'AGS' trouvée dans la table.")
                taux_text = cells[4].get_text() # Le taux employeur est dans la 5ème cellule (index 4)
                taux_ags = parse_taux(taux_text)
                break # On a trouvé, on sort de la boucle
        
        if taux_ags is not None:
            print(f"Taux AGS (patronal) trouvé : {taux_ags*100:.2f}%")
            return taux_ags
        
        raise ValueError("Impossible d'extraire le taux AGS de la table chômage.")

    except Exception as e:
        print(f"ERREUR : Le scraping a échoué. Raison : {e}")
        return None
    finally:
        if driver:
            print("Fermeture du navigateur Selenium.")
            driver.quit()

def update_config_file(nouveau_taux: float):
    try:
        with open(FICHIER_TAUX, 'r', encoding='utf-8') as f:
            config = json.load(f)
        cotisation = config['TAUX_COTISATIONS']['ags']
        ancien_taux = cotisation['patronal']
        if ancien_taux == nouveau_taux:
            print(f"Le taux AGS dans '{FICHIER_TAUX}' est déjà correct ({nouveau_taux}).")
            return
        print(f"Mise à jour du taux AGS (patronal) : {ancien_taux} -> {nouveau_taux}")
        cotisation['patronal'] = nouveau_taux
        with open(FICHIER_TAUX, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        print(f"✅ Le fichier '{FICHIER_TAUX}' a été mis à jour avec succès.")
    except Exception as e:
        print(f"ERREUR : Une erreur est survenue lors de la mise à jour : {e}")


if __name__ == "__main__":
    taux = get_taux_ags_legisocial()
    
    if taux is not None:
        update_config_file(taux)