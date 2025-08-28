# scripts/vieillessesalarial.py

import json
import re
import requests
from bs4 import BeautifulSoup

FICHIER_TAUX = 'config/taux_cotisations.json'
URL_URSSAF = "https://www.urssaf.fr/accueil/outils-documentation/taux-baremes/taux-cotisations-secteur-prive.html"

def get_taux_vieillesse_salarial() -> dict | None:
    """
    Scrape le site de l'URSSAF pour trouver les taux de l'assurance vieillesse salariale
    en ciblant spécifiquement la section "salarié".
    Retourne un dictionnaire avec les taux ou None si erreur.
    """
    try:
        print(f" scraping de l'URL : {URL_URSSAF}...")
        r = requests.get(URL_URSSAF, timeout=20, headers={
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
        })
        r.raise_for_status()

        soup = BeautifulSoup(r.text, "html.parser")
        
        # --- NOUVELLE LOGIQUE DE CIBLAGE ---
        # 1. Trouver toutes les sections "article" qui contiennent les tableaux
        articles = soup.find_all('article')
        salarie_section_text = ""
        
        # 2. Parcourir les sections pour trouver celle qui concerne le salarié
        for article in articles:
            h2 = article.find('h2', class_='h4-like')
            if h2 and 'taux de cotisations salarié' in h2.get_text(strip=True).lower():
                salarie_section_text = article.get_text(" ", strip=True)
                break # On a trouvé la bonne section, on arrête la boucle

        if not salarie_section_text:
            raise ValueError("La section 'Taux de cotisations salarié' est introuvable dans le HTML.")

        # 3. Appliquer la recherche (regex) uniquement sur le texte de la bonne section
        motif = r"Assurance vieillesse\s*([0-9,]+)\s*%\s*sur la totalité et\s*([0-9,]+)\s*%\s*dans la limite du plafond"
        m = re.search(motif, salarie_section_text, flags=re.IGNORECASE)
        
        if not m:
            raise ValueError("Motif des taux d'assurance vieillesse salariale introuvable.")
        
        # Extraire, convertir et arrondir les deux taux
        taux_deplafond_str = m.group(1).replace(",", ".")
        taux_plafond_str = m.group(2).replace(",", ".")
        
        taux_deplafond = round(float(taux_deplafond_str) / 100.0, 5)
        taux_plafond = round(float(taux_plafond_str) / 100.0, 5)
        
        print(f" Taux vieillesse déplafonné (salarial) trouvé : {taux_deplafond*100:.2f}%")
        print(f" Taux vieillesse plafonné (salarial) trouvé   : {taux_plafond*100:.2f}%")
        
        return {"deplafond": taux_deplafond, "plafond": taux_plafond}
        
    except Exception as e:
        print(f"ERREUR : Le scraping a échoué. Raison : {e}")
        return None

def update_config_file(nouveaux_taux: dict):
    """
    Lit le fichier JSON des taux et met à jour les deux taux de retraite salariale.
    """
    try:
        with open(FICHIER_TAUX, 'r', encoding='utf-8') as f:
            config = json.load(f)
        
        cotisation_deplafond = config['TAUX_COTISATIONS']['retraite_secu_deplafond']
        cotisation_plafond = config['TAUX_COTISATIONS']['retraite_secu_plafond']

        print(f"Mise à jour de 'retraite_secu_deplafond' (salarial) : {cotisation_deplafond['salarial']} -> {nouveaux_taux['deplafond']}")
        print(f"Mise à jour de 'retraite_secu_plafond' (salarial)   : {cotisation_plafond['salarial']} -> {nouveaux_taux['plafond']}")

        cotisation_deplafond['salarial'] = nouveaux_taux['deplafond']
        cotisation_plafond['salarial'] = nouveaux_taux['plafond']
        
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
    taux = get_taux_vieillesse_salarial()
    
    if taux is not None:
        update_config_file(taux)