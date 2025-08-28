# scripts/PSS.py

import json
import re
import requests
from bs4 import BeautifulSoup

FICHIER_ENTREPRISE = 'config/parametres_entreprise.json'
URL_URSSAF = "https://www.urssaf.fr/accueil/outils-documentation/taux-baremes/plafonds-securite-sociale.html"

def parse_valeur_numerique(text: str) -> int:
    """
    Nettoie et convertit un texte contenant un montant en entier.
    Exemple : "3 925 €" -> 3925
    """
    if not text: return 0
    # Supprime les espaces insécables, les espaces normaux et le symbole €
    cleaned_text = text.replace('\xa0', '').replace(' ', '').replace('€', '').strip()
    return int(cleaned_text)

def get_plafonds_ss() -> dict | None:
    """
    Scrape le site de l'URSSAF pour récupérer l'ensemble des plafonds de la SS.
    Retourne un dictionnaire structuré ou None si erreur.
    """
    try:
        print(f" scraping de l'URL : {URL_URSSAF}...")
        r = requests.get(URL_URSSAF, timeout=20, headers={
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
        })
        r.raise_for_status()

        soup = BeautifulSoup(r.text, "html.parser")
        
        # 1. Cibler la section principale "métropole et en Outre-mer"
        main_section = soup.find('div', id='metropole-outre-mer')
        if not main_section:
            raise ValueError("Section principale des plafonds (ID: metropole-outre-mer) introuvable.")

        # Dictionnaire pour mapper les libellés du site aux clés de notre JSON
        key_mapping = {
            'Année': 'annuel',
            'Trimestre': 'trimestriel',
            'Mois': 'mensuel',
            'Quinzaine': 'quinzaine',
            'Semaine': 'hebdomadaire',
            'Jour': 'journalier',
            'Heure': 'horaire'
        }
        
        plafonds = {}
        table_rows = main_section.find_all('tr', class_='table_custom__tbody')
        
        # 2. Itérer sur chaque ligne du tableau
        for row in table_rows:
            header_cell = row.find('th')
            value_cell = row.find('td')
            
            if header_cell and value_cell:
                libelle = header_cell.get_text(strip=True)
                if libelle in key_mapping:
                    json_key = key_mapping[libelle]
                    valeur = parse_valeur_numerique(value_cell.get_text())
                    plafonds[json_key] = valeur
                    print(f"  - Plafond '{libelle}' trouvé : {valeur} €")

        if len(plafonds) != len(key_mapping):
            raise ValueError(f"Tous les plafonds n'ont pas été trouvés. Attendu: {len(key_mapping)}, Trouvé: {len(plafonds)}")
            
        return plafonds

    except Exception as e:
        print(f"ERREUR : Le scraping a échoué. Raison : {e}")
        return None

def update_config_file(nouveaux_plafonds: dict):
    """
    Met à jour le fichier parametres_entreprise.json avec le nouvel objet des plafonds.
    """
    try:
        with open(FICHIER_ENTREPRISE, 'r', encoding='utf-8') as f:
            config = json.load(f)
        
        constantes = config['PARAMETRES_ENTREPRISE']['constantes_paie_2025']
        
        if constantes.get('plafonds_securite_sociale') == nouveaux_plafonds:
            print(f"Les plafonds de la SS dans '{FICHIER_ENTREPRISE}' sont déjà à jour.")
            return

        print("Mise à jour de l'objet des plafonds de la Sécurité Sociale...")
        constantes['plafonds_securite_sociale'] = nouveaux_plafonds
        
        # Supprimer l'ancienne clé si elle existe pour garder le fichier propre
        if 'plafond_ss_mensuel' in constantes:
            del constantes['plafond_ss_mensuel']
        
        with open(FICHIER_ENTREPRISE, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
            
        print(f"✅ Le fichier '{FICHIER_ENTREPRISE}' a été mis à jour avec succès.")
        
    except Exception as e:
        print(f"ERREUR : Une erreur est survenue lors de la mise à jour : {e}")


if __name__ == "__main__":
    valeurs_plafonds = get_plafonds_ss()
    
    if valeurs_plafonds is not None:
        update_config_file(valeurs_plafonds)