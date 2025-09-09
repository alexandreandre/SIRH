# scripts/saisie-arret.py

import json
import re
import requests
from bs4 import BeautifulSoup

FICHIER_ENTREPRISE = 'config/parametres_entreprise.json'
URL_SERVICE_PUBLIC = "https://www.service-public.fr/particuliers/actualites/A15377" # Note: Ceci est une ancienne URL pour l'exemple

def parse_valeur_numerique(text):
    """Utilitaire pour nettoyer et convertir un texte en nombre."""
    if not text: return 0.0
    cleaned = text.replace('€', '').replace('\xa0', '').replace(' ', '').replace(',', '.')
    match = re.search(r"([0-9]+\.?[0-9]*)", cleaned)
    return float(match.group(1)) if match else 0.0

def get_bareme_saisie() -> dict | None:
    """
    Scrape le site service-public.fr pour trouver le barème de saisie sur salaire
    et le montant du Solde Bancaire Insaisissable (SBI).
    """
    try:
        # Note : L'URL devra être mise à jour pour l'année 2025 quand elle sera disponible
        # Pour l'instant, nous utilisons la structure connue.
        print(f" scraping de l'URL : {URL_SERVICE_PUBLIC}...")
        r = requests.get(URL_SERVICE_PUBLIC, timeout=20, headers={
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
        })
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        
        donnees_saisie = {}

        # --- 1. Scraper le Solde Bancaire Insaisissable (SBI) ---
        sbi_motif = r"(?:montant forfaitaire du RSA.*est de|Le montant du SBI est de)\s*([0-9,]+\s*€)"
        match_sbi = re.search(sbi_motif, soup.get_text(" ", strip=True), re.IGNORECASE)
        if match_sbi:
            sbi_valeur = parse_valeur_numerique(match_sbi.group(1))
            donnees_saisie['sbi'] = sbi_valeur
            print(f"  - Solde Bancaire Insaisissable (SBI) trouvé : {sbi_valeur} €")

        # --- 2. Scraper le barème de saisie ---
        bareme_header = soup.find(lambda tag: tag.name in ['h3', 'h2'] and 'Barème' in tag.text and 'saisissable' in tag.text)
        if bareme_header:
            bareme_table = bareme_header.find_next('table')
            bareme = []
            if bareme_table and bareme_table.find('tbody'):
                rows = bareme_table.find('tbody').find_all('tr')
                for row in rows:
                    cells = row.find_all(['th', 'td'])
                    if len(cells) < 2: continue # On s'assure d'avoir au moins 2 colonnes
                    
                    tranche_texte = cells[0].get_text(strip=True)
                    
                    # --- FILTRE CORRIGÉ ---
                    # On ne traite que les lignes qui contiennent des montants ou le mot "supérieur"
                    if "€" not in tranche_texte and "supérieur à" not in tranche_texte.lower():
                        continue

                    quotite_texte = cells[1].get_text(strip=True)
                    
                    matches = re.findall(r"([0-9\s\xa0,]+\.?[0-9]*)", tranche_texte.replace('.', ''))
                    tranche_max = parse_valeur_numerique(matches[-1]) if matches else float('inf')

                    match_quotite = re.search(r"(\d+)/(\d+)", quotite_texte)
                    if "¼" in quotite_texte: quotite_saisissable = 0.25
                    elif "1/3" in quotite_texte: quotite_saisissable = round(1/3, 4)
                    elif "2/3" in quotite_texte: quotite_saisissable = round(2/3, 4)
                    elif match_quotite: quotite_saisissable = round(int(match_quotite.group(1)) / int(match_quotite.group(2)), 4)
                    else: quotite_saisissable = 1.0 # Pour la ligne "supérieur à..."

                    bareme.append({
                        "tranche_plafond": tranche_max,
                        "quotite_saisissable": quotite_saisissable
                    })
                donnees_saisie['bareme'] = bareme
                print(f"  - Barème de saisie sur salaire trouvé ({len(bareme)} tranches).")

        if len(donnees_saisie) < 2:
            raise ValueError("Impossible de trouver toutes les données de saisie sur salaire.")
            
        return donnees_saisie
        
    except Exception as e:
        print(f"ERREUR : Le scraping a échoué. Raison : {e}")
        return None

def update_config_file(nouvelles_valeurs: dict):
    # Cette fonction ne change pas
    try:
        with open(FICHIER_ENTREPRISE, 'r', encoding='utf-8') as f:
            config = json.load(f)
        
        saisie_config = config['PARAMETRES_ENTREPRISE']['constantes_paie_2025']['saisie_sur_salaire']
        
        print("\nMise à jour du fichier de configuration...")
        saisie_config['solde_bancaire_insaisissable'] = nouvelles_valeurs['sbi']
        saisie_config['bareme_mensuel'] = nouvelles_valeurs['bareme']
        
        with open(FICHIER_ENTREPRISE, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
            
        print(f"✅ Le fichier '{FICHIER_ENTREPRISE}' a été mis à jour avec succès.")
        
    except Exception as e:
        print(f"ERREUR : Une erreur est survenue lors de la mise à jour : {e}")

if __name__ == "__main__":
    valeurs = get_bareme_saisie()
    
    if valeurs is not None:
        update_config_file(valeurs)