# scripts/FNAL_LegiSocial.py

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
    Nettoie un texte (ex: "0,10 %"), le convertit en float (0.10)
    puis en taux réel (0.0010).
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

def get_taux_fnal_legisocial() -> dict | None:
    """
    Scrape le site LegiSocial pour trouver les deux taux de la cotisation FNAL.
    Retourne un dictionnaire avec les deux taux.
    """
    try:
        print(f"Scraping de l'URL : {URL_LEGISOCIAL}...")
        response = requests.get(URL_LEGISOCIAL, timeout=20, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.0.0 Safari/537.36"
        })
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")
        
        # 1. Trouver la table principale des cotisations de 2025
        table_title = soup.find(lambda tag: tag.name in ['h2', 'h3'] and 'Quels sont les taux de cotisations en 2025' in tag.get_text())
        if not table_title:
            raise ValueError("Titre de la table principale des cotisations 2025 introuvable.")
            
        table = table_title.find_next('table')
        if not table:
            raise ValueError("Table des cotisations introuvable après le titre.")

        # 2. Parcourir les lignes pour trouver les deux taux du FNAL
        taux_trouves = {}
        for row in table.find('tbody').find_all('tr'):
            cells = row.find_all('td')
            if len(cells) > 4:
                libelle = cells[0].get_text().lower()
                if "fnal" in libelle:
                    taux_text = cells[4].get_text()
                    taux = parse_taux(taux_text)
                    
                    if taux is not None:
                        # On détermine si c'est le taux pour les petites ou grandes entreprises
                        if "moins de 50" in libelle:
                            print(f"Taux FNAL (< 50 salariés) trouvé : {taux*100:.2f}%")
                            taux_trouves['moins_de_50'] = taux
                        elif "au moins 50" in libelle:
                            print(f"Taux FNAL (>= 50 salariés) trouvé : {taux*100:.2f}%")
                            taux_trouves['au_moins_50'] = taux
        
        if "moins_de_50" in taux_trouves and "au_moins_50" in taux_trouves:
            return taux_trouves
        else:
            raise ValueError("Impossible de trouver les deux taux FNAL (<50 et >=50).")

    except Exception as e:
        print(f"ERREUR : Le scraping a échoué. Raison : {e}")
        return None

def update_config_file(nouveau_taux: float):
    """
    Met à jour le fichier de configuration avec le taux FNAL applicable.
    """
    try:
        with open(FICHIER_TAUX, 'r', encoding='utf-8') as f:
            config = json.load(f)
        
        cotisation = config['TAUX_COTISATIONS']['fnal']
        ancien_taux = cotisation['patronal']

        if ancien_taux == nouveau_taux:
            print(f"Le taux FNAL dans '{FICHIER_TAUX}' est déjà correct ({nouveau_taux}).")
            return

        print(f"Mise à jour du taux FNAL (patronal) : {ancien_taux} -> {nouveau_taux}")
        cotisation['patronal'] = nouveau_taux
        
        with open(FICHIER_TAUX, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
            
        print(f"✅ Le fichier '{FICHIER_TAUX}' a été mis à jour avec succès.")
        
    except Exception as e:
        print(f"ERREUR : Une erreur est survenue lors de la mise à jour : {e}")


if __name__ == "__main__":
    tous_les_taux = get_taux_fnal_legisocial()
    
    if tous_les_taux:
        try:
            with open(FICHIER_ENTREPRISE, 'r', encoding='utf-8') as f:
                config_entreprise = json.load(f)
            
            conditions = config_entreprise['PARAMETRES_ENTREPRISE']['conditions_cotisations']
            effectif = conditions.get('effectif_total')
            
            if effectif is None:
                raise KeyError("La clé 'effectif_total' est manquante.")
            
            est_inferieur_a_50 = (effectif < 50)

            if est_inferieur_a_50:
                taux_final = tous_les_taux['moins_de_50']
                print(f"\nEffectif < 50 détecté. Application du taux : {taux_final*100:.2f}%")
            else:
                taux_final = tous_les_taux['au_moins_50']
                print(f"\nEffectif >= 50 détecté. Application du taux : {taux_final*100:.2f}%")
            
            update_config_file(taux_final)

        except Exception as e:
            print(f"ERREUR lors de la sélection du taux à appliquer : {e}")