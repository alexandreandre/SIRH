# scripts/MMIDsalarial_LegiSocial.py

import json
import re
import requests
from bs4 import BeautifulSoup

# --- Fichiers et URL cibles ---
FICHIER_CONTRAT = 'config/parametres_contrat.json'
FICHIER_TAUX = 'config/taux_cotisations.json'
URL_LEGISOCIAL = "https://www.legisocial.fr/reperes-sociaux/taux-cotisations-sociales-urssaf-2025.html"

def parse_taux(text: str) -> float | None:
    """
    Nettoie un texte (ex: "1,30 %"), le convertit en float (1.30)
    puis en taux réel (0.0130).
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

def get_taux_alsace_moselle_legisocial() -> float | None:
    """
    Scrape le site LegiSocial pour trouver le taux salarial maladie du régime Alsace-Moselle.
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

        for row in table.find('tbody').find_all('tr'):
            cells = row.find_all('td')
            if len(cells) > 3:
                libelle = cells[0].get_text().lower()
                if "maladie" in libelle and "alsace-moselle" in libelle:
                    # Le taux salarial est dans la 4ème colonne (index 3)
                    taux_text = cells[3].get_text()
                    taux = parse_taux(taux_text)
                    
                    if taux is not None:
                        print(f"Taux salarial maladie (Alsace-Moselle) trouvé : {taux*100:.2f}%")
                        # On prend la première occurrence qui est la bonne
                        return taux
        
        raise ValueError("Ligne correspondant au régime Alsace-Moselle introuvable.")

    except Exception as e:
        print(f"ERREUR : Le scraping a échoué. Raison : {e}")
        return None

def update_config_file(nouveau_taux: float):
    """
    Met à jour le fichier de configuration avec le taux applicable.
    """
    try:
        with open(FICHIER_TAUX, 'r', encoding='utf-8') as f:
            config_taux = json.load(f)

        cotisation_maladie = config_taux['TAUX_COTISATIONS']['securite_sociale_maladie']
        taux_actuel = cotisation_maladie['salarial']
        
        if taux_actuel == nouveau_taux:
            print(f"Le taux salarial maladie dans '{FICHIER_TAUX}' est déjà correct ({nouveau_taux}).")
            return

        print(f"Mise à jour du taux salarial maladie : {taux_actuel} -> {nouveau_taux}")
        cotisation_maladie['salarial'] = nouveau_taux

        with open(FICHIER_TAUX, 'w', encoding='utf-8') as f:
            json.dump(config_taux, f, indent=2, ensure_ascii=False)
        print(f"✅ Le fichier '{FICHIER_TAUX}' a été mis à jour avec succès.")
        
    except Exception as e:
        print(f"ERREUR : Une erreur est survenue lors de la mise à jour : {e}")


if __name__ == "__main__":
    try:
        with open(FICHIER_CONTRAT, 'r', encoding='utf-8') as f:
            config_contrat = json.load(f)
        
        is_alsace_moselle = config_contrat['PARAMETRES_CONTRAT']['poste'].get('isAlsaceMoselle', False)

        taux_final = 0.0
        if is_alsace_moselle:
            print("Régime Alsace-Moselle détecté. Recherche du taux spécifique...")
            taux_specifique = get_taux_alsace_moselle_legisocial()
            if taux_specifique is None:
                # Arrêt propre si le scraping échoue pour ne pas mettre une mauvaise valeur
                print("Impossible de continuer sans le taux Alsace-Moselle.")
                exit()
            taux_final = taux_specifique
        else:
            print("Régime général détecté. Le taux salarial maladie est de 0%.")

        update_config_file(taux_final)

    except Exception as e:
        print(f"ERREUR dans le script principal : {e}")