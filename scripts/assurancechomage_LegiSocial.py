# scripts/assurancechomage_LegiSocial.py

import json
import re
import requests
from bs4 import BeautifulSoup
from datetime import datetime

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

def get_taux_chomage_legisocial() -> float | None:
    """
    Scrape le site LegiSocial en utilisant Requests et BeautifulSoup.
    """
    try:
        # --- Utilisation de Requests au lieu de Selenium ---
        print(f"Scraping de l'URL avec Requests : {URL_LEGISOCIAL}...")
        response = requests.get(URL_LEGISOCIAL, timeout=20, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.0.0 Safari/537.36"
        })
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")
        
        # --- La logique de parsing reste la même ---
        all_headers = soup.find_all('h3')
        chomage_header = None
        for header in all_headers:
            if 'Cotisations chômage' in header.get_text():
                chomage_header = header
                print("Titre de la section 'Cotisations chômage' trouvé !")
                break 
        
        if not chomage_header:
            raise ValueError("Titre 'Cotisations chômage' introuvable. Le site bloque probablement Requests.")
        
        table = chomage_header.find_next('table')
        if not table:
            raise ValueError("Table des cotisations chômage introuvable après le titre.")

        month_map = {
            'janvier': 1, 'février': 2, 'mars': 3, 'avril': 4, 'mai': 5, 'juin': 6,
            'juillet': 7, 'août': 8, 'septembre': 9, 'octobre': 10, 'novembre': 11, 'décembre': 12
        }
        rates_by_date = []
        for row in table.find('tbody').find_all('tr'):
            cells = row.find_all('td')
            if len(cells) > 4 and "Assurance chômage" in cells[0].get_text():
                libelle = cells[0].get_text().lower()
                
                match = re.search(r'(\d{1,2})\w*\s*(\w+)\s*(\d{4})', libelle)
                if match:
                    day = int(match.group(1))
                    month_name = match.group(2)
                    year = int(match.group(3))
                    
                    start_date = datetime(year, month_map[month_name], day).date()
                    taux = parse_taux(cells[4].get_text())
                    
                    if taux is not None:
                        print(f"Ligne trouvée : Taux de {taux*100:.2f}% à partir du {start_date.strftime('%d/%m/%Y')}")
                        rates_by_date.append({'date_debut': start_date, 'taux': taux})

        if not rates_by_date:
            raise ValueError("Aucun taux d'assurance chômage avec date n'a pu être extrait.")

        date_actuelle = datetime.now().date()
        taux_applicable = None
        rates_by_date.sort(key=lambda x: x['date_debut'])
        
        for rate_info in rates_by_date:
            if date_actuelle >= rate_info['date_debut']:
                taux_applicable = rate_info['taux']
        
        if taux_applicable is not None:
            print(f"\n=> Taux applicable au {date_actuelle.strftime('%d/%m/%Y')} : {taux_applicable*100:.2f}%")
            return taux_applicable
        
        raise ValueError("Impossible de déterminer le taux applicable à la date d'aujourd'hui.")

    except Exception as e:
        print(f"ERREUR : Le scraping a échoué. Raison : {e}")
        return None

def update_config_file(nouveau_taux: float):
    # Cette fonction ne change pas
    try:
        with open(FICHIER_TAUX, 'r', encoding='utf-8') as f:
            config = json.load(f)
        cotisation = config['TAUX_COTISATIONS']['assurance_chomage']
        ancien_taux = cotisation['patronal']
        if ancien_taux == nouveau_taux:
            print(f"Le taux d'assurance chômage dans '{FICHIER_TAUX}' est déjà correct ({nouveau_taux}).")
            return
        print(f"Mise à jour du taux d'assurance chômage (patronal) : {ancien_taux} -> {nouveau_taux}")
        cotisation['patronal'] = nouveau_taux
        with open(FICHIER_TAUX, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        print(f"✅ Le fichier '{FICHIER_TAUX}' a été mis à jour avec succès.")
    except Exception as e:
        print(f"ERREUR : Une erreur est survenue lors de la mise à jour : {e}")


if __name__ == "__main__":
    taux = get_taux_chomage_legisocial()
    
    if taux is not None:
        update_config_file(taux)