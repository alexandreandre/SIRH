# scripts/vieillessepatronal.py

import json
import re
import requests
from bs4 import BeautifulSoup

FICHIER_TAUX = 'config/taux_cotisations.json'
URL_URSSAF = "https://www.urssaf.fr/accueil/outils-documentation/taux-baremes/taux-cotisations-secteur-prive.html"

def get_taux_vieillesse_patronal() -> dict | None:
    """
    Scrape le site de l'URSSAF pour trouver les taux de l'assurance vieillesse patronale
    en ciblant spécifiquement la section "employeur" avec une méthode robuste.
    """
    try:
        print(f" scraping de l'URL : {URL_URSSAF}...")
        r = requests.get(URL_URSSAF, timeout=20, headers={
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
        })
        r.raise_for_status()

        soup = BeautifulSoup(r.text, "html.parser")
        
        # --- LOGIQUE DE CIBLAGE AMÉLIORÉE ---
        
        # 1. Isoler la section "employeur"
        articles = soup.find_all('article')
        employeur_section = None
        for article in articles:
            h2 = article.find('h2', class_='h4-like')
            if h2 and 'taux de cotisations employeur' in h2.get_text(strip=True).lower():
                employeur_section = article
                break

        if not employeur_section:
            raise ValueError("La section 'Taux de cotisations employeur' est introuvable dans le HTML.")

        # 2. Parcourir chaque ligne (tr) du tableau de cette section
        table_rows = employeur_section.find_all('tr', class_='table_custom__tbody')
        for row in table_rows:
            header_cell = row.find('th')
            # 3. Si l'en-tête de ligne est celui de l'Assurance vieillesse...
            if header_cell and 'Assurance vieillesse' in header_cell.get_text(strip=True):
                value_cell = row.find('td')
                if not value_cell:
                    raise ValueError("Ligne 'Assurance vieillesse' trouvée, mais cellule de valeur manquante.")
                
                # 4. ...appliquer le regex sur cette cellule uniquement
                value_text = value_cell.get_text(strip=True)
                motif = r"([0-9,]+)\s*%\s*sur la totalité et\s*([0-9,]+)\s*%\s*dans la limite du plafond"
                m = re.search(motif, value_text, flags=re.IGNORECASE)
                
                if not m:
                    raise ValueError(f"Taux d'assurance vieillesse patronale introuvables dans la cellule : '{value_text}'")

                taux_deplafond_str = m.group(1).replace(",", ".")
                taux_plafond_str = m.group(2).replace(",", ".")
                
                taux_deplafond = round(float(taux_deplafond_str) / 100.0, 5)
                taux_plafond = round(float(taux_plafond_str) / 100.0, 5)
                
                print(f" Taux vieillesse déplafonné (patronal) trouvé : {taux_deplafond*100:.2f}%")
                print(f" Taux vieillesse plafonné (patronal) trouvé   : {taux_plafond*100:.2f}%")
                
                return {"deplafond": taux_deplafond, "plafond": taux_plafond}

        raise ValueError("Ligne 'Assurance vieillesse' introuvable dans le tableau employeur.")
        
    except Exception as e:
        print(f"ERREUR : Le scraping a échoué. Raison : {e}")
        return None

def update_config_file(nouveaux_taux: dict):
    """
    Lit le fichier JSON des taux et met à jour les deux taux de retraite patronale.
    """
    try:
        with open(FICHIER_TAUX, 'r', encoding='utf-8') as f:
            config = json.load(f)
        
        cotisation_deplafond = config['TAUX_COTISATIONS']['retraite_secu_deplafond']
        cotisation_plafond = config['TAUX_COTISATIONS']['retraite_secu_plafond']

        print(f"Mise à jour de 'retraite_secu_deplafond' (patronal) : {cotisation_deplafond['patronal']} -> {nouveaux_taux['deplafond']}")
        print(f"Mise à jour de 'retraite_secu_plafond' (patronal)   : {cotisation_plafond['patronal']} -> {nouveaux_taux['plafond']}")

        cotisation_deplafond['patronal'] = nouveaux_taux['deplafond']
        cotisation_plafond['patronal'] = nouveaux_taux['plafond']
        
        with open(FICHIER_TAUX, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
            
        print(f"✅ Le fichier '{FICHIER_TAUX}' a été mis à jour avec succès.")
        
    except FileNotFoundError:
        print(f"ERREUR : Le fichier de configuration '{FICHIER_TAUX}' est introuvable.")
    except KeyError as e:
        print(f"ERREUR : La structure du fichier '{FICHIER_TAUX}' est incorrecte. La clé {e} est manquante.")
    except Exception as e:
        print(f"ERREUR : Une erreur est survenue lors de la mise à jour du fichier : {e}")


if __name__ == "__main__":
    taux = get_taux_vieillesse_patronal()
    
    if taux is not None:
        update_config_file(taux)