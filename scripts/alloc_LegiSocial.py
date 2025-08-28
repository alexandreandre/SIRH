# scripts/alloc_LegiSocial.py

import json
import re
import requests
from bs4 import BeautifulSoup

# --- Fichiers et URL cibles ---
FICHIER_ENTREPRISE = 'config/parametres_entreprise.json'
FICHIER_TAUX = 'config/taux_cotisations.json'
URL_LEGISOCIAL = "https://www.legisocial.fr/reperes-sociaux/taux-cotisations-sociales-urssaf-2025.html"

def parse_taux(text: str) -> float | None:
    """
    Nettoie un texte (ex: "3,45 %"), le convertit en float (3.45)
    puis en taux réel (0.0345).
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

def get_taux_alloc_legisocial() -> dict | None:
    """
    Scrape le site LegiSocial pour trouver les taux plein et réduit des allocations familiales.
    Retourne un dictionnaire avec les deux taux.
    """
    try:
        print(f"Scraping de l'URL : {URL_LEGISOCIAL}...")
        response = requests.get(URL_LEGISOCIAL, timeout=20, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.0.0 Safari/537.36"
        })
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")
        
        # 1. Trouver la table principale des cotisations
        table_title = soup.find(lambda tag: tag.name in ['h2', 'h3'] and 'Quels sont les taux' in tag.get_text())
        if not table_title:
            raise ValueError("Titre de la table principale des cotisations introuvable.")
            
        table = table_title.find_next('table')
        if not table:
            raise ValueError("Table des cotisations introuvable après le titre.")

        # 2. Parcourir les lignes pour trouver les deux taux
        taux_trouves = {}
        for row in table.find('tbody').find_all('tr'):
            cells = row.find_all('td')
            if len(cells) > 4:
                libelle = cells[0].get_text().lower()
                if "allocations familiales" in libelle:
                    taux_text = cells[4].get_text()
                    taux = parse_taux(taux_text)
                    
                    if taux is not None:
                        # On détermine si c'est le taux plein ou réduit
                        if "≤" in libelle or "<" in libelle:
                            print(f"Taux Allocations Familiales (réduit) trouvé : {taux*100:.2f}%")
                            taux_trouves['reduit'] = taux
                        elif ">" in libelle:
                            print(f"Taux Allocations Familiales (plein) trouvé : {taux*100:.2f}%")
                            taux_trouves['plein'] = taux
        
        if "reduit" in taux_trouves and "plein" in taux_trouves:
            return taux_trouves
        else:
            raise ValueError("Impossible de trouver les deux taux (réduit et plein) pour les allocations familiales.")

    except Exception as e:
        print(f"ERREUR : Le scraping a échoué. Raison : {e}")
        return None

def update_config_file(nouveau_taux: float):
    """
    Met à jour le fichier de configuration avec le taux applicable.
    """
    try:
        with open(FICHIER_TAUX, 'r', encoding='utf-8') as f:
            config = json.load(f)
        
        cotisation = config['TAUX_COTISATIONS']['allocations_familiales']
        ancien_taux = cotisation['patronal']

        if ancien_taux == nouveau_taux:
            print(f"Le taux dans '{FICHIER_TAUX}' est déjà correct ({nouveau_taux}). Aucune modification.")
            return

        print(f"Mise à jour du taux d'allocations familiales (patronal) : {ancien_taux} -> {nouveau_taux}")
        cotisation['patronal'] = nouveau_taux
        
        with open(FICHIER_TAUX, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
            
        print(f"✅ Le fichier '{FICHIER_TAUX}' a été mis à jour avec succès.")
        
    except Exception as e:
        print(f"ERREUR : Une erreur est survenue lors de la mise à jour : {e}")


if __name__ == "__main__":
    tous_les_taux = get_taux_alloc_legisocial()
    
    if tous_les_taux:
        try:
            with open(FICHIER_ENTREPRISE, 'r', encoding='utf-8') as f:
                config_entreprise = json.load(f)
            
            conditions = config_entreprise['PARAMETRES_ENTREPRISE']['conditions_cotisations']
            appliquer_taux_reduit = conditions.get('remuneration_annuelle_brute_inferieure_3.5_smic', False)

            if appliquer_taux_reduit:
                taux_final = tous_les_taux['reduit']
                print(f"\nCondition 'inférieure à 3.5 SMIC' active. Application du taux réduit : {taux_final*100:.2f}%")
            else:
                taux_final = tous_les_taux['plein']
                print(f"\nCondition 'supérieure à 3.5 SMIC' active. Application du taux plein : {taux_final*100:.2f}%")
            
            update_config_file(taux_final)

        except Exception as e:
            print(f"ERREUR lors de la sélection du taux à appliquer : {e}")