# scripts/Avantages.py

import json
import re
import requests
from bs4 import BeautifulSoup

FICHIER_ENTREPRISE = 'config/parametres_entreprise.json'
URL_URSSAF = "https://www.urssaf.fr/accueil/outils-documentation/taux-baremes/avantages-en-nature.html"

def parse_valeur_numerique(text):
    """
    Fonction utilitaire robuste pour nettoyer et convertir un texte
    contenant une valeur numérique (avec €, %, espaces, etc.) en nombre.
    """
    if not text: return 0.0
    cleaned_text = text.replace(',', '.').replace('€', '').replace('\xa0', '').replace(' ', '')
    match = re.search(r"([0-9]+\.?[0-9]*)", cleaned_text)
    if match:
        return float(match.group(1))
    return 0.0

def get_valeurs_avantages() -> dict | None:
    """
    Scrape le site de l'URSSAF pour trouver les valeurs des avantages en nature
    avec une méthode de scraping sécurisée.
    """
    try:
        print(f" scraping de l'URL : {URL_URSSAF}...")
        r = requests.get(URL_URSSAF, timeout=20, headers={
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
        })
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        
        valeurs_trouvees = {}

        # --- LOGIQUE DE SCRAPING CORRIGÉE POUR "REPAS" ---
        repas_header = soup.find('h2', id='ancre-repas')
        if repas_header:
            repas_table = repas_header.find_next('table')
            if repas_table:
                rows = repas_table.find_all('tr')
                for row in rows:
                    header_cell = row.find('th')
                    # On utilise un regex pour trouver "1 repas" de manière flexible
                    if header_cell and re.search(r"1\s+repas", header_cell.get_text(strip=True)):
                        value_cell = row.find('td')
                        if value_cell:
                            valeur_repas = parse_valeur_numerique(value_cell.get_text())
                            valeurs_trouvees['repas'] = valeur_repas
                            print(f"  - Valeur pour 1 repas trouvée : {valeur_repas} €")
                            break # On a trouvé, on sort de la boucle

        # --- Scraper l'exonération maximale pour les titres-restaurant ---
        tr_header = soup.find('h2', id='ancre-titre-restaurant')
        if tr_header:
            tr_table = tr_header.find_next('table')
            if tr_table:
                header_cell = tr_table.find(lambda tag: tag.name == 'th' and 'Exonération maximale' in tag.get_text())
                if header_cell:
                    row = header_cell.find_parent('tr')
                    if row and row.find('td'):
                        valeur_tr = parse_valeur_numerique(row.find('td').get_text())
                        valeurs_trouvees['titre_restaurant'] = valeur_tr
                        print(f"  - Exonération max. titre-restaurant trouvée : {valeur_tr} €")

        # --- Scraper le barème logement ---
        logement_header = soup.find('h2', id='ancre-logement')
        if logement_header:
            logement_table = logement_header.find_next('table')
            bareme = []
            if logement_table and logement_table.find('tbody'):
                rows = logement_table.find('tbody').find_all('tr')
                for row in rows:
                    cells = row.find_all(['th', 'td'])
                    if len(cells) < 3: continue
                    
                    tranche_texte = cells[0].get_text(strip=True)
                    matches = re.findall(r"([0-9\s\xa0,]+)", tranche_texte)
                    rem_max = parse_valeur_numerique(matches[-1]) if matches else float('inf')
                    
                    valeur_1_piece = parse_valeur_numerique(cells[1].get_text())
                    valeur_par_piece = parse_valeur_numerique(cells[2].get_text())
                    
                    bareme.append({
                        "remuneration_max": rem_max,
                        "valeur_1_piece": valeur_1_piece,
                        "valeur_par_piece": valeur_par_piece
                    })
                if bareme:
                    valeurs_trouvees['logement'] = bareme
                    print(f"  - Barème logement complet trouvé ({len(bareme)} tranches).")

        if len(valeurs_trouvees) < 3:
            raise ValueError(f"Impossible de trouver toutes les valeurs. Trouvées : {list(valeurs_trouvees.keys())}")
            
        return valeurs_trouvees
        
    except Exception as e:
        print(f"ERREUR : Le scraping a échoué. Raison : {e}")
        return None

def update_config_file(nouvelles_valeurs: dict):
    """
    Met à jour le fichier parametres_entreprise.json avec les nouvelles valeurs.
    """
    try:
        with open(FICHIER_ENTREPRISE, 'r', encoding='utf-8') as f:
            config = json.load(f)
        
        if 'avantages_en_nature' not in config['PARAMETRES_ENTREPRISE']:
            config['PARAMETRES_ENTREPRISE']['avantages_en_nature'] = {}
            
        avantages = config['PARAMETRES_ENTREPRISE']['avantages_en_nature']
        
        print("\nMise à jour du fichier de configuration...")
        avantages['repas_valeur_forfaitaire'] = nouvelles_valeurs['repas']
        avantages['titre_restaurant_exoneration_max_patronale'] = nouvelles_valeurs['titre_restaurant']
        avantages['logement_bareme_forfaitaire'] = nouvelles_valeurs['logement']
        
        with open(FICHIER_ENTREPRISE, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
            
        print(f"✅ Le fichier '{FICHIER_ENTREPRISE}' a été mis à jour avec succès.")
        
    except Exception as e:
        print(f"ERREUR : Une erreur est survenue lors de la mise à jour : {e}")

if __name__ == "__main__":
    valeurs = get_valeurs_avantages()
    
    if valeurs is not None:
        update_config_file(valeurs)