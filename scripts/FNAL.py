# scripts/FNAL.py

import json
import re
import requests
from bs4 import BeautifulSoup

# Définir les chemins des fichiers
FICHIER_ENTREPRISE = 'config/parametres_entreprise.json'
FICHIER_TAUX = 'config/taux_cotisations.json'
URL_URSSAF = "https://www.urssaf.fr/accueil/outils-documentation/taux-baremes/taux-cotisations-secteur-prive.html"

def get_taux_fnal(is_effectif_inferieur_50: bool) -> float | None:
    """
    Scrape le site de l'URSSAF pour trouver le taux FNAL en fonction de l'effectif
    de l'entreprise, avec une méthode de recherche de texte améliorée.
    """
    try:
        print(f" scraping de l'URL : {URL_URSSAF}...")
        r = requests.get(URL_URSSAF, timeout=20, headers={
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
        })
        r.raise_for_status()

        soup = BeautifulSoup(r.text, "html.parser")
        
        articles = soup.find_all('article')
        employeur_section = None
        for article in articles:
            h2 = article.find('h2', class_='h4-like')
            if h2 and 'taux de cotisations employeur' in h2.get_text(strip=True).lower():
                employeur_section = article
                break

        if not employeur_section:
            raise ValueError("Section 'Taux de cotisations employeur' introuvable.")

        if is_effectif_inferieur_50:
            motif_recherche = r"Fnal\s+\(effectif\s+de\s+moins\s+de\s+50\s+salariés\)"
            effectif_log = "< 50 salariés"
        else:
            motif_recherche = r"Fnal\s+\(effectif\s+de\s+50\s+salariés\s+et\s+plus\)"
            effectif_log = ">= 50 salariés"
            
        print(f"Recherche du taux FNAL pour l'effectif : '{effectif_log}'")

        table_rows = employeur_section.find_all('tr', class_='table_custom__tbody')
        for row in table_rows:
            header_cell = row.find('th')
            if header_cell and re.search(motif_recherche, header_cell.get_text(strip=True, separator=" "), flags=re.IGNORECASE):
                value_cell = row.find('td')
                if not value_cell:
                    raise ValueError(f"Ligne FNAL trouvée, mais cellule de valeur manquante.")
                
                value_text = value_cell.get_text(strip=True)
                m = re.search(r"([0-9,]+)\s*%", value_text)
                if not m:
                    raise ValueError(f"Taux FNAL introuvable dans la cellule : '{value_text}'")
                
                taux_str = m.group(1).replace(",", ".")
                taux = round(float(taux_str) / 100.0, 5)
                
                print(f" Taux trouvé : {taux*100:.2f}%")
                return taux

        raise ValueError(f"Ligne pour le taux FNAL ({effectif_log}) introuvable dans le tableau.")
        
    except Exception as e:
        print(f"ERREUR : Le scraping a échoué. Raison : {e}")
        return None

def update_config_file(nouveau_taux: float):
    """
    Lit le fichier JSON des taux et met à jour le taux patronal du FNAL.
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
        
    except FileNotFoundError:
        print(f"ERREUR : Le fichier '{FICHIER_TAUX}' est introuvable.")
    except KeyError as e:
        print(f"ERREUR : La structure du fichier '{FICHIER_TAUX}' est incorrecte. La clé {e} est manquante.")
    except Exception as e:
        print(f"ERREUR : Une erreur est survenue lors de la mise à jour : {e}")


if __name__ == "__main__":
    try:
        with open(FICHIER_ENTREPRISE, 'r', encoding='utf-8') as f:
            config_entreprise = json.load(f)
        
        # --- LOGIQUE CORRIGÉE POUR LE NOUVEAU FORMAT ---
        # 1. Lire le nombre de salariés depuis la bonne sous-section
        conditions = config_entreprise['PARAMETRES_ENTREPRISE']['conditions_cotisations']
        effectif = conditions.get('effectif_total')
        
        if effectif is None:
            raise KeyError("La clé 'effectif_total' est manquante dans parametres_entreprise.json")

        # 2. Effectuer la comparaison pour obtenir un booléen
        est_inferieur_a_50 = (effectif < 50)
        
        # 3. Passer ce booléen à la fonction de scraping
        taux = get_taux_fnal(is_effectif_inferieur_50=est_inferieur_a_50)
    
        if taux is not None:
            update_config_file(taux)

    except FileNotFoundError:
        print(f"ERREUR : Le fichier '{FICHIER_ENTREPRISE}' est introuvable.")
    except (KeyError, TypeError) as e:
        print(f"ERREUR : La structure du fichier '{FICHIER_ENTREPRISE}' est incorrecte ou une clé est manquante : {e}")