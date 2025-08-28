# scripts/AGS.py

import json
import re
import requests
from bs4 import BeautifulSoup

FICHIER_ENTREPRISE = 'config/parametres_entreprise.json'
FICHIER_TAUX = 'config/taux_cotisations.json'
URL_URSSAF = "https://www.urssaf.fr/accueil/outils-documentation/taux-baremes/taux-cotisations-secteur-prive.html"

def get_taux_ags(is_ett: bool) -> float | None:
    """
    Scrape le site de l'URSSAF pour trouver le taux de la cotisation AGS,
    en choisissant le taux général ou celui pour les entreprises de travail temporaire (ETT).
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

        # Trouver la ligne "Cotisation AGS"
        table_rows = employeur_section.find_all('tr', class_='table_custom__tbody')
        value_text = ""
        for row in table_rows:
            header_cell = row.find('th')
            if header_cell and 'Cotisation AGS' in header_cell.get_text(strip=True):
                value_cell = row.find('td')
                if not value_cell:
                    raise ValueError("Ligne 'AGS' trouvée, mais cellule de valeur manquante.")
                value_text = value_cell.get_text(" ", strip=True)
                break
        
        if not value_text:
            raise ValueError("Ligne 'Cotisation AGS' introuvable.")
        
        # Déterminer quel motif chercher
        if is_ett:
            motif_recherche = r"([0-9,]+)\s*%\s*pour les entreprises de travail temporaire"
            cas_log = "pour Entreprise de Travail Temporaire"
        else:
            # Le taux général est le premier pourcentage trouvé qui N'EST PAS celui des ETT
            motif_recherche = r"^.*?([0-9,]+)\s*%"
            cas_log = "général"

        print(f"Recherche du taux AGS : cas '{cas_log}'")
        m = re.search(motif_recherche, value_text, flags=re.IGNORECASE | re.DOTALL)

        if not m:
            raise ValueError(f"Motif pour le taux AGS ({cas_log}) introuvable.")
            
        taux_str = m.group(1).replace(",", ".")
        taux = round(float(taux_str) / 100.0, 5)
        
        print(f" Taux trouvé : {taux*100:.2f}%")
        return taux
        
    except Exception as e:
        print(f"ERREUR : Le scraping a échoué. Raison : {e}")
        return None

def update_config_file(nouveau_taux: float):
    """
    Lit le fichier JSON des taux et met à jour le taux patronal de l'AGS.
    """
    try:
        with open(FICHIER_TAUX, 'r', encoding='utf-8') as f:
            config = json.load(f)
        
        cotisation = config['TAUX_COTISATIONS']['ags']
        ancien_taux = cotisation['patronal']

        if ancien_taux == nouveau_taux:
            print(f"Le taux AGS dans '{FICHIER_TAUX}' est déjà correct ({nouveau_taux}).")
            return

        print(f"Mise à jour du taux AGS (patronal) : {ancien_taux} -> {nouveau_taux}")
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
        
        conditions = config_entreprise['PARAMETRES_ENTREPRISE']['conditions_cotisations']
        est_ett = conditions.get('est_entreprise_travail_temporaire', False)

        taux = get_taux_ags(is_ett=est_ett)
    
        if taux is not None:
            update_config_file(taux)

    except FileNotFoundError:
        print(f"ERREUR : Le fichier '{FICHIER_ENTREPRISE}' est introuvable.")
    except KeyError as e:
        print(f"ERREUR : La structure du fichier '{FICHIER_ENTREPRISE}' est incorrecte ou une clé est manquante : {e}")