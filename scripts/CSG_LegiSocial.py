# scripts/CSG_LegiSocial.py

import json
import re
import requests
from bs4 import BeautifulSoup

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

def get_taux_csg_crds_legisocial() -> dict | None:
    """
    Scrape le site LegiSocial pour trouver les taux de la CSG/CRDS,
    en gérant correctement l'attribut rowspan.
    """
    try:
        print(f"Scraping de l'URL : {URL_LEGISOCIAL}...")
        response = requests.get(URL_LEGISOCIAL, timeout=20, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.0.0 Safari/537.36"
        })
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")
        
        all_headers = soup.find_all('h3')
        csg_header = None
        for header in all_headers:
            if 'COTISATIONS CSG et CRDS' in header.get_text():
                csg_header = header
                print("Titre de la section 'COTISATIONS CSG et CRDS' trouvé !")
                break

        if not csg_header:
            raise ValueError("Titre de la section 'COTISATIONS CSG et CRDS' introuvable.")
            
        table = csg_header.find_next('table')
        if not table:
            raise ValueError("Table des cotisations CSG/CRDS introuvable après le titre.")

        taux_bruts = {}
        for row in table.find('tbody').find_all('tr'):
            cells = row.find_all('td')
            
            # --- LOGIQUE CORRIGÉE POUR GÉRER LE ROWSPAN ---
            # On détermine l'index de la colonne du taux "Salarié"
            # S'il y a 5 cellules (1ère ligne), c'est la 4ème (index 3).
            # S'il y en a 4 (lignes suivantes), c'est la 3ème (index 2).
            salarie_col_index = 3 if len(cells) >= 5 else 2

            # On vérifie si la ligne a assez de colonnes pour notre index
            if len(cells) > salarie_col_index:
                libelle = cells[0].get_text(strip=True)
                taux_text = cells[salarie_col_index].get_text()
                
                if "CSG déductible" in libelle and 'deductible' not in taux_bruts:
                    taux_bruts['deductible'] = parse_taux(taux_text)
                elif "CSG non déductible" in libelle and 'non_deductible_csg' not in taux_bruts:
                    taux_bruts['non_deductible_csg'] = parse_taux(taux_text)
                elif "CRDS non déductible" in libelle and 'non_deductible_crds' not in taux_bruts:
                    taux_bruts['non_deductible_crds'] = parse_taux(taux_text)
            
            if len(taux_bruts) == 3:
                break
        
        if len(taux_bruts) != 3 or None in taux_bruts.values():
            raise ValueError(f"Impossible de trouver les 3 taux CSG/CRDS. Trouvés : {taux_bruts}")

        print(f"Taux bruts extraits : {taux_bruts}")

        taux_final_deductible = taux_bruts['deductible']
        taux_final_non_deductible = taux_bruts['non_deductible_csg'] + taux_bruts['non_deductible_crds']

        return {"deductible": taux_final_deductible, "non_deductible": round(taux_final_non_deductible, 5)}

    except Exception as e:
        print(f"ERREUR : Le scraping a échoué. Raison : {e}")
        return None

def update_config_file(nouveaux_taux: dict):
    """
    Fonction identique à celle du script original.
    """
    try:
        with open(FICHIER_TAUX, 'r', encoding='utf-8') as f:
            config = json.load(f)
        
        cotisation_deductible = config['TAUX_COTISATIONS']['csg_deductible']
        cotisation_non_deductible = config['TAUX_COTISATIONS']['csg_crds_non_deductible']

        print(f"\nMise à jour de 'csg_deductible' (salarial) : {cotisation_deductible['salarial']} -> {nouveaux_taux['deductible']}")
        print(f"Mise à jour de 'csg_crds_non_deductible' (salarial) : {cotisation_non_deductible['salarial']} -> {nouveaux_taux['non_deductible']}")

        cotisation_deductible['salarial'] = nouveaux_taux['deductible']
        cotisation_non_deductible['salarial'] = nouveaux_taux['non_deductible']
        
        with open(FICHIER_TAUX, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
            
        print(f"✅ Le fichier '{FICHIER_TAUX}' a été mis à jour avec succès.")
        
    except Exception as e:
        print(f"ERREUR : Une erreur est survenue lors de la mise à jour : {e}")

if __name__ == "__main__":
    taux = get_taux_csg_crds_legisocial()
    
    if taux is not None:
        update_config_file(taux)