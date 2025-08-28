# scripts/assurancechomage.py

import json
import re
import requests
from datetime import datetime
from bs4 import BeautifulSoup

FICHIER_TAUX = 'config/taux_cotisations.json'
URL_URSSAF = "https://www.urssaf.fr/accueil/outils-documentation/taux-baremes/taux-cotisations-secteur-prive.html"

def get_taux_chomage() -> float | None:
    """
    Scrape le site de l'URSSAF pour trouver le taux de l'assurance chômage
    applicable à la date actuelle.
    """
    try:
        print(f" scraping de l'URL : {URL_URSSAF}...")
        r = requests.get(URL_URSSAF, timeout=20, headers={
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
        })
        r.raise_for_status()

        soup = BeautifulSoup(r.text, "html.parser")
        
        # 1. Isoler la section "employeur"
        articles = soup.find_all('article')
        employeur_section = None
        for article in articles:
            h2 = article.find('h2', class_='h4-like')
            if h2 and 'taux de cotisations employeur' in h2.get_text(strip=True).lower():
                employeur_section = article
                break
        if not employeur_section:
            raise ValueError("Section 'Taux de cotisations employeur' introuvable.")

        # 2. Trouver la ligne "Contribution assurance chômage"
        table_rows = employeur_section.find_all('tr', class_='table_custom__tbody')
        value_text = ""
        for row in table_rows:
            header_cell = row.find('th')
            if header_cell and 'Contribution assurance chômage' in header_cell.get_text(strip=True):
                value_cell = row.find('td')
                if not value_cell:
                    raise ValueError("Ligne 'Assurance chômage' trouvée, mais cellule de valeur manquante.")
                value_text = value_cell.get_text(" ", strip=True)
                break
        
        if not value_text:
            raise ValueError("Ligne 'Contribution assurance chômage' introuvable.")
            
        # 3. Extraire les deux taux avec leurs dates
        motif_avant = r"Jusqu’au\s*(\d{2}/\d{2}/\d{4})\s*:\s*([0-9,]+)\s*%"
        motif_apres = r"partir du\s*(\d{2}/\d{2}/\d{4})\s*:\s*([0-9,]+)\s*%"

        match_avant = re.search(motif_avant, value_text)
        match_apres = re.search(motif_apres, value_text)

        if not match_avant or not match_apres:
            raise ValueError("Impossible d'extraire les deux taux basés sur les dates.")
            
        # 4. Comparer la date actuelle à la date charnière
        date_charniere_str = match_apres.group(1)
        date_charniere = datetime.strptime(date_charniere_str, "%d/%m/%Y").date()
        date_actuelle = datetime.now().date()
        
        if date_actuelle < date_charniere:
            taux_str = match_avant.group(2)
            print(f"Date actuelle ({date_actuelle.strftime('%d/%m/%Y')}) est avant la date charnière ({date_charniere_str}). Application du premier taux.")
        else:
            taux_str = match_apres.group(2)
            print(f"Date actuelle ({date_actuelle.strftime('%d/%m/%Y')}) est après ou égale à la date charnière ({date_charniere_str}). Application du second taux.")

        taux = round(float(taux_str.replace(",", ".")) / 100.0, 5)
        print(f" Taux sélectionné : {taux*100:.2f}%")
        return taux
        
    except Exception as e:
        print(f"ERREUR : Le scraping a échoué. Raison : {e}")
        return None

def update_config_file(nouveau_taux: float):
    """
    Lit le fichier JSON des taux et met à jour le taux patronal de l'assurance chômage.
    """
    try:
        with open(FICHIER_TAUX, 'r', encoding='utf-8') as f:
            config = json.load(f)
        
        cotisation = config['TAUX_COTISATIONS']['assurance_chomage']
        ancien_taux = cotisation['patronal']

        if ancien_taux == nouveau_taux:
            print(f"Le taux d'assurance chômage dans '{FICHIER_TAUX}' est déjà correct ({nouveau_taux}).")
            return

        print(f"Mise à jour du taux d'assurance chômage (patronal) : {ancien_taux} -> {nouveau_taux}")
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
    taux = get_taux_chomage()
    
    if taux is not None:
        update_config_file(taux)