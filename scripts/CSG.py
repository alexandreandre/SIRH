# scripts/CSG.py

import json
import re
import requests
from bs4 import BeautifulSoup

FICHIER_TAUX = 'config/taux_cotisations.json'
URL_URSSAF = "https://www.urssaf.fr/accueil/outils-documentation/taux-baremes/taux-cotisations-secteur-prive.html"

def get_taux_csg_crds() -> dict | None:
    """
    Scrape le site de l'URSSAF pour trouver les taux de la CSG déductible,
    CSG non déductible et CRDS.
    Retourne un dictionnaire avec les taux finaux ou None si erreur.
    """
    try:
        print(f" scraping de l'URL : {URL_URSSAF}...")
        r = requests.get(URL_URSSAF, timeout=20, headers={
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
        })
        r.raise_for_status()

        soup = BeautifulSoup(r.text, "html.parser")
        
        # 1. Isoler la section "salarié" cette fois-ci
        articles = soup.find_all('article')
        salarie_section = None
        for article in articles:
            h2 = article.find('h2', class_='h4-like')
            if h2 and 'taux de cotisations salarié' in h2.get_text(strip=True).lower():
                salarie_section = article
                break
        if not salarie_section:
            raise ValueError("Section 'Taux de cotisations salarié' introuvable.")

        # 2. Parcourir les lignes du tableau pour extraire les 3 taux
        taux_trouves = {}
        lignes_a_chercher = {
            "csg_imposable": "CSG imposable",
            "csg_non_imposable": "CSG non imposable",
            "crds": "CRDS"
        }
        
        table_rows = salarie_section.find_all('tr', class_='table_custom__tbody')
        for cle, texte in lignes_a_chercher.items():
            for row in table_rows:
                header_cell = row.find('th')
                if header_cell and texte in header_cell.get_text(strip=True):
                    value_cell = row.find('td')
                    if not value_cell: continue
                    
                    value_text = value_cell.get_text(strip=True)
                    m = re.search(r"([0-9,]+)\s*%", value_text)
                    if not m: continue

                    taux_str = m.group(1).replace(",", ".")
                    taux = round(float(taux_str) / 100.0, 5)
                    taux_trouves[cle] = taux
                    print(f" Taux '{texte}' trouvé : {taux*100:.2f}%")
                    break
        
        if len(taux_trouves) != 3:
            raise ValueError(f"Impossible de trouver les 3 taux CSG/CRDS. Trouvés : {taux_trouves.keys()}")
            
        # 3. Calculer les taux finaux pour le JSON
        taux_deductible = taux_trouves["csg_non_imposable"]
        taux_non_deductible = taux_trouves["csg_imposable"] + taux_trouves["crds"]
        
        print(f"Calcul du taux non déductible : {taux_trouves['csg_imposable']} + {taux_trouves['crds']} = {taux_non_deductible:.4f}")

        return {"deductible": taux_deductible, "non_deductible": round(taux_non_deductible, 5)}
        
    except Exception as e:
        print(f"ERREUR : Le scraping a échoué. Raison : {e}")
        return None

def update_config_file(nouveaux_taux: dict):
    """
    Lit le fichier JSON des taux et met à jour les lignes CSG/CRDS.
    """
    try:
        with open(FICHIER_TAUX, 'r', encoding='utf-8') as f:
            config = json.load(f)
        
        cotisation_deductible = config['TAUX_COTISATIONS']['csg_deductible']
        cotisation_non_deductible = config['TAUX_COTISATIONS']['csg_crds_non_deductible']

        print(f"Mise à jour de 'csg_deductible' (salarial) : {cotisation_deductible['salarial']} -> {nouveaux_taux['deductible']}")
        print(f"Mise à jour de 'csg_crds_non_deductible' (salarial) : {cotisation_non_deductible['salarial']} -> {nouveaux_taux['non_deductible']}")

        cotisation_deductible['salarial'] = nouveaux_taux['deductible']
        cotisation_non_deductible['salarial'] = nouveaux_taux['non_deductible']
        
        with open(FICHIER_TAUX, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
            
        print(f"✅ Le fichier '{FICHIER_TAUX}' a été mis à jour avec succès.")
        
    except FileNotFoundError:
        print(f"ERREUR : Le fichier '{FICHIER_TAUX}' est introuvable.")
    except KeyError as e:
        print(f"ERREUR : La structure du fichier '{FICHIER_TAUX}' est incorrecte. La clé {e} est manquante.")
    except Exception as e:
        print(f"ERREUR : Une erreur est survenue lors de la mise à jour : {e}")


if __name__ == "__main__":
    taux = get_taux_csg_crds()
    
    if taux is not None:
        update_config_file(taux)