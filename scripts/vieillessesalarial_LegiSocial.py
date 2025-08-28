# scripts/vieillessesalarial_LegiSocial.py

import json
import re
import requests
from bs4 import BeautifulSoup

# --- Fichiers et URL cibles ---
FICHIER_TAUX = 'config/taux_cotisations.json'
URL_LEGISOCIAL = "https://www.legisocial.fr/reperes-sociaux/taux-cotisations-sociales-urssaf-2025.html"

def parse_taux(text: str) -> float | None:
    """
    Nettoie un texte (ex: "6,90 %"), le convertit en float (6.90)
    puis en taux réel (0.0690).
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

def get_taux_vieillesse_salarial_legisocial() -> dict | None:
    """
    Scrape le site LegiSocial pour trouver les taux de l'assurance vieillesse salariale.
    """
    try:
        print(f"Scraping de l'URL : {URL_LEGISOCIAL}...")
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

        taux_trouves = {}
        for row in table.find('tbody').find_all('tr'):
            cells = row.find_all('td')
            if len(cells) > 3: # On a besoin d'au moins 4 colonnes
                libelle = cells[0].get_text(strip=True).lower()
                
                # La colonne du taux salarial est la 4ème (index 3)
                taux_text = cells[3].get_text()
                
                if "vieillesse déplafonnée" in libelle:
                    taux = parse_taux(taux_text)
                    if taux is not None:
                        print(f"Taux Vieillesse Déplafonnée (salarial) trouvé : {taux*100:.2f}%")
                        taux_trouves['deplafond'] = taux

                elif "vieillesse plafonnée" in libelle:
                    taux = parse_taux(taux_text)
                    if taux is not None:
                        print(f"Taux Vieillesse Plafonnée (salarial) trouvé : {taux*100:.2f}%")
                        taux_trouves['plafond'] = taux

        if "deplafond" in taux_trouves and "plafond" in taux_trouves:
            return taux_trouves
        else:
            raise ValueError("Impossible de trouver les deux taux de vieillesse (plafonné et déplafonné).")

    except Exception as e:
        print(f"ERREUR : Le scraping a échoué. Raison : {e}")
        return None

def update_config_file(nouveaux_taux: dict):
    """
    Met à jour le fichier de configuration avec les nouveaux taux.
    """
    try:
        with open(FICHIER_TAUX, 'r', encoding='utf-8') as f:
            config = json.load(f)
        
        cotisation_deplafond = config['TAUX_COTISATIONS']['retraite_secu_deplafond']
        cotisation_plafond = config['TAUX_COTISATIONS']['retraite_secu_plafond']

        print(f"\nMise à jour de 'retraite_secu_deplafond' (salarial) : {cotisation_deplafond['salarial']} -> {nouveaux_taux['deplafond']}")
        print(f"Mise à jour de 'retraite_secu_plafond' (salarial)   : {cotisation_plafond['salarial']} -> {nouveaux_taux['plafond']}")

        cotisation_deplafond['salarial'] = nouveaux_taux['deplafond']
        cotisation_plafond['salarial'] = nouveaux_taux['plafond']
        
        with open(FICHIER_TAUX, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
            
        print(f"✅ Le fichier '{FICHIER_TAUX}' a été mis à jour avec succès.")
        
    except Exception as e:
        print(f"ERREUR : Une erreur est survenue lors de la mise à jour : {e}")

if __name__ == "__main__":
    taux = get_taux_vieillesse_salarial_legisocial()
    
    if taux is not None:
        update_config_file(taux)