# scripts/CSA_LegiSocial.py

import json
import re
import requests
from bs4 import BeautifulSoup

# --- Fichiers et URL cibles ---
FICHIER_TAUX = 'config/taux_cotisations.json'
URL_LEGISOCIAL = "https://www.legisocial.fr/reperes-sociaux/taux-cotisations-sociales-urssaf-2025.html"

def parse_taux(text: str) -> float | None:
    """
    Nettoie un texte (ex: "0,30 %"), le convertit en float (0.30)
    puis en taux réel (0.0030).
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

def get_taux_csa_legisocial() -> float | None:
    """
    Scrape le site LegiSocial pour trouver le taux de la Contribution Solidarité Autonomie.
    """
    try:
        print(f"Scraping de l'URL : {URL_LEGISOCIAL}...")
        response = requests.get(URL_LEGISOCIAL, timeout=20, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.0.0 Safari/537.36"
        })
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")
        
        # 1. Trouver le titre exact que vous avez spécifié
        table_title = soup.find(lambda tag: tag.name in ['h2', 'h3'] and 'Quels sont les taux de cotisations en 2025' in tag.get_text())
        if not table_title:
            raise ValueError("Titre 'Quels sont les taux de cotisations en 2025 ?' introuvable.")
        print("Titre de la section principale trouvé.")
            
        table = table_title.find_next('table')
        if not table:
            raise ValueError("Table des cotisations introuvable après le titre.")

        # 2. Parcourir les lignes pour trouver celle de la CSA
        for row in table.find('tbody').find_all('tr'):
            cells = row.find_all('td')
            if len(cells) > 4:
                libelle = cells[0].get_text(strip=True)
                if "Contribution de solidarité pour l'autonomie" in libelle:
                    print("Ligne 'Contribution de solidarité pour l'autonomie' trouvée.")
                    # Le taux patronal est dans la 5ème colonne (index 4)
                    taux_text = cells[4].get_text()
                    taux = parse_taux(taux_text)
                    
                    if taux is not None:
                        print(f"Taux CSA trouvé : {taux*100:.2f}%")
                        return taux
        
        raise ValueError("Ligne correspondant à la CSA introuvable dans la table.")

    except Exception as e:
        print(f"ERREUR : Le scraping a échoué. Raison : {e}")
        return None

def update_config_file(nouveau_taux: float):
    """
    Met à jour le fichier de configuration avec le nouveau taux.
    """
    try:
        with open(FICHIER_TAUX, 'r', encoding='utf-8') as f:
            config = json.load(f)
        
        cotisation = config['TAUX_COTISATIONS']['csa']
        ancien_taux = cotisation['patronal']

        if ancien_taux == nouveau_taux:
            print(f"Le taux CSA dans '{FICHIER_TAUX}' est déjà correct ({nouveau_taux}).")
            return

        print(f"Mise à jour du taux CSA (patronal) : {ancien_taux} -> {nouveau_taux}")
        cotisation['patronal'] = nouveau_taux
        
        with open(FICHIER_TAUX, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
            
        print(f"✅ Le fichier '{FICHIER_TAUX}' a été mis à jour avec succès.")
        
    except Exception as e:
        print(f"ERREUR : Une erreur est survenue lors de la mise à jour : {e}")


if __name__ == "__main__":
    taux = get_taux_csa_legisocial()
    
    if taux is not None:
        update_config_file(taux)