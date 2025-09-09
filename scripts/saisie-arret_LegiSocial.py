# scripts/saisie-arret_LegiSocial.py

import json
import re
import requests
from bs4 import BeautifulSoup

# --- Fichiers et URL cibles ---
FICHIER_ENTREPRISE = 'config/parametres_entreprise.json'
URL_LEGISOCIAL = "https://www.legisocial.fr/reperes-sociaux/bareme-saisie-remuneration-salaire-2025.html"

def parse_valeur_numerique(text: str) -> float:
    """Nettoie et convertit un texte en nombre."""
    if not text: return 0.0
    cleaned = text.replace('€', '').replace('\xa0', '').replace(' ', '').replace('.', '').replace(',', '.')
    match = re.search(r"([0-9]+\.?[0-9]*)", cleaned)
    return float(match.group(1)) if match else 0.0

def parse_quotite(text: str) -> float:
    """Convertit une fraction ou un texte en nombre décimal."""
    text = text.lower().strip()
    if "¼" in text: return 0.25
    if "1/3" in text: return round(1/3, 4)
    if "2/3" in text: return round(2/3, 4)
    if "totalité" in text: return 1.0
    match = re.match(r"(\d+)/(\d+)", text)
    if match:
        return round(int(match.group(1)) / int(match.group(2)), 4)
    return 0.0

def get_bareme_saisie_legisocial() -> dict | None:
    """
    Scrape le site LegiSocial pour trouver le barème MENSUEL de saisie, le SBI et la majoration.
    """
    try:
        print(f"Scraping de l'URL : {URL_LEGISOCIAL}...")
        response = requests.get(URL_LEGISOCIAL, timeout=20, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.0.0 Safari/537.36"
        })
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        
        donnees_saisie = {}

        # --- 1. Scraper le Solde Bancaire Insaisissable (SBI) ---
        sbi_header = soup.find(lambda tag: tag.name in ['h2', 'h3'] and 'quotité insaisissable' in tag.get_text().lower())
        if sbi_header:
            sbi_list = sbi_header.find_next_sibling('ul')
            if sbi_list:
                for item in sbi_list.find_all('li'):
                    if "depuis le 1er avril" in item.get_text():
                        sbi_match = re.search(r'([0-9,]+\s*€)', item.get_text())
                        if sbi_match:
                            donnees_saisie['sbi'] = parse_valeur_numerique(sbi_match.group(1))
                            print(f"  - Solde Bancaire Insaisissable (SBI) trouvé : {donnees_saisie['sbi']} €")
                            break
        
        # --- 2. Scraper le barème MENSUEL de saisie et la majoration ---
        # --- LOGIQUE CORRIGÉE : On trouve la table par son titre INTERNE "Barème mensuel" ---
        monthly_table_title_cell = soup.find(lambda tag: tag.name == 'td' and 'barème mensuel' in tag.get_text(strip=True).lower())
        if not monthly_table_title_cell:
            raise ValueError("Impossible de trouver la cellule de titre 'Barème mensuel'.")
    
        table = monthly_table_title_cell.find_parent('table')
        if not table:
            raise ValueError("Impossible de trouver la table parente du barème mensuel.")
        
        bareme_mensuel = []
        for row in table.find('tbody').find_all('tr'):
            row_text = row.get_text().lower()
            if "majoration pour personne à charge" in row_text:
                majoration_match = re.search(r'([0-9.,]+\s*€)', row_text)
                if majoration_match:
                    donnees_saisie['majoration'] = parse_valeur_numerique(majoration_match.group(1))
                    print(f"  - Majoration par personne à charge trouvée : {donnees_saisie['majoration']} €")
            else:
                cells = row.find_all('td')
                if len(cells) == 2 and ("€" in cells[0].get_text() or "totalité" in cells[1].get_text().lower()):
                    tranche_text = cells[0].get_text()
                    quotite_text = cells[1].get_text()
                    
                    all_numbers_str = re.findall(r'[0-9\.]+,[0-9]+', tranche_text)
                    tranche_max = None # Pour la dernière tranche "Plus de..."
                    if all_numbers_str:
                        tranche_max = parse_valeur_numerique(all_numbers_str[-1])
                    
                    bareme_mensuel.append({
                        "tranche_plafond": tranche_max,
                        "quotite_saisissable": parse_quotite(quotite_text)
                    })
        
        donnees_saisie['bareme'] = bareme_mensuel
        print(f"  - Barème de saisie MENSUEL trouvé ({len(bareme_mensuel)} tranches).")

        if len(donnees_saisie) < 3:
            raise ValueError(f"Impossible de trouver toutes les données. Trouvées: {donnees_saisie.keys()}")
            
        return donnees_saisie
        
    except Exception as e:
        print(f"ERREUR : Le scraping a échoué. Raison : {e}")
        return None

def update_config_file(nouvelles_valeurs: dict):
    """Met à jour le fichier parametres_entreprise.json."""
    try:
        with open(FICHIER_ENTREPRISE, 'r', encoding='utf-8') as f:
            config = json.load(f)
        
        saisie_config = config['PARAMETRES_ENTREPRISE']['constantes_paie_2025']['saisie_sur_salaire']
        
        print("\nMise à jour du fichier de configuration...")
        saisie_config['solde_bancaire_insaisissable'] = nouvelles_valeurs['sbi']
        saisie_config['bareme_mensuel'] = nouvelles_valeurs['bareme']
        saisie_config['majoration_par_personne_a_charge'] = nouvelles_valeurs['majoration']
        
        with open(FICHIER_ENTREPRISE, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
            
        print(f"✅ Le fichier '{FICHIER_ENTREPRISE}' a été mis à jour avec succès.")
        
    except Exception as e:
        print(f"ERREUR : Une erreur est survenue lors de la mise à jour : {e}")

if __name__ == "__main__":
    valeurs = get_bareme_saisie_legisocial()
    
    if valeurs is not None:
        update_config_file(valeurs)