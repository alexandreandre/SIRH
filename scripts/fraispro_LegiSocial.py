# scripts/fraispro_LegiSocial.py

import json
import re
import requests
from bs4 import BeautifulSoup

# --- Fichiers et URL cibles ---
FICHIER_BAREMES = 'config/baremes.json'
URL_LEGISOCIAL = "https://www.legisocial.fr/reperes-sociaux/allocations-forfaitaires-frais-professionnels-2025.html"

def parse_valeur_numerique(text: str) -> float:
    """Nettoie et convertit un texte en nombre (float)."""
    if not text: return 0.0
    cleaned = text.replace('€', '').replace('\xa0', '').replace('\u202f', '').replace(' ', '').replace(',', '.')
    match = re.search(r"([0-9]+\.?[0-9]*)", cleaned)
    return float(match.group(1)) if match else 0.0

def scrape_repas_legisocial(soup: BeautifulSoup) -> dict:
    """Scrape la section des indemnités de repas."""
    data = {}
    header = soup.find('h2', string=re.compile(r'Allocations frais de repas', re.I))
    if not header: return data
    
    table = header.find_next('table')
    if not table: return data

    rows = table.find_all('tr')
    for row in rows:
        cells = row.find_all('td')
        if len(cells) == 2:
            libelle = cells[0].get_text().lower()
            valeur = parse_valeur_numerique(cells[1].get_text())
            
            if "sur son lieu de travail" in libelle:
                data["sur_lieu_travail"] = valeur
            elif "non contraint" in libelle:
                data["hors_locaux_sans_restaurant"] = valeur
            elif "repas au restaurant" in libelle:
                data["hors_locaux_avec_restaurant"] = valeur
    
    print(f"  - Barème Repas trouvé : {data}")
    return data

def scrape_grand_deplacement_legisocial(soup: BeautifulSoup) -> dict:
    """Scrape la section des indemnités de grand déplacement."""
    data = {"metropole": []}
    header = soup.find('h2', string=re.compile(r'grand déplacement', re.I))
    if not header: return data
    
    table = header.find_next('table')
    if not table: return data
    
    # On pré-remplit la structure pour les 3 périodes
    periods = ["Pour les 3 premiers mois", "Au-delà du 3 ème mois", "Au-delà du 24 ème mois"]
    data['metropole'] = [{'periode_sejour': p, 'repas': 0, 'logement_paris_banlieue': 0, 'logement_province': 0} for p in periods]

    repas, logement_paris, logement_province = [], [], []
    current_list = None
    
    for row in table.find_all('tr'):
        text = row.get_text(strip=True)
        if "Par repas" in text:
            current_list = repas
        elif "Paris et les départements" in text:
            current_list = logement_paris
        elif "autres départements" in text:
            current_list = logement_province
        
        cells = row.find_all('td')
        if len(cells) == 2 and "€" in cells[1].get_text():
            valeur = parse_valeur_numerique(cells[1].get_text())
            if current_list is not None:
                current_list.append(valeur)
    
    # On assemble les données collectées
    for i in range(min(len(repas), len(logement_paris), len(logement_province))):
        data['metropole'][i]['repas'] = repas[i]
        data['metropole'][i]['logement_paris_banlieue'] = logement_paris[i]
        data['metropole'][i]['logement_province'] = logement_province[i]

    print(f"  - Barème Grand Déplacement trouvé.")
    return data


def scrape_mutation_legisocial(soup: BeautifulSoup) -> dict:
    """Scrape la section mobilité / mutation professionnelle."""
    data = {"hebergement_provisoire": {}, "hebergement_definitif": {}}
    header = soup.find('h2', string=re.compile(r'mobilité professionnelle', re.I))
    if not header: return data
    
    table = header.find_next('table')
    if not table: return data

    for row in table.find_all('tr'):
        cells = row.find_all('td')
        if len(cells) == 2:
            libelle = cells[0].get_text().lower()
            valeur_cell = cells[1]

            if "hébergement provisoire" in libelle:
                data["hebergement_provisoire"]["montant_par_jour"] = parse_valeur_numerique(valeur_cell.get_text())
            elif "installation dans le nouveau logement" in libelle:
                data["hebergement_definitif"]["frais_installation"] = parse_valeur_numerique(valeur_cell.get_text())
            elif "majoré de par enfant" in libelle:
                # Cette cellule contient deux valeurs dans des balises <p> séparées
                valeurs = [parse_valeur_numerique(p.get_text()) for p in valeur_cell.find_all('p')]
                if len(valeurs) == 2:
                    data["hebergement_definitif"]["majoration_par_enfant"] = valeurs[0]
                    data["hebergement_definitif"]["plafond_total"] = valeurs[1]

    print(f"  - Barème Mutation Professionnelle trouvé.")
    return data

def get_and_update_baremes_legisocial():
    try:
        print(f"Scraping de l'URL : {URL_LEGISOCIAL}...")
        response = requests.get(URL_LEGISOCIAL, timeout=20, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.0.0 Safari/537.36"
        })
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        
        # Scraper les données des sections disponibles sur LegiSocial
        repas_data = scrape_repas_legisocial(soup)
        grand_deplacement_data = scrape_grand_deplacement_legisocial(soup)
        mutation_data = scrape_mutation_legisocial(soup)

        # On ouvre le fichier de configuration existant
        with open(FICHIER_BAREMES, 'r', encoding='utf-8') as f:
            config = json.load(f)
        
        print("\nMise à jour du fichier de configuration...")
        frais_pro = config['FRAIS_PROFESSIONNELS_2025']
        
        # On met à jour uniquement les clés qu'on a pu scraper
        if repas_data:
            frais_pro['repas_indemnites'] = repas_data
        if grand_deplacement_data.get('metropole'):
            frais_pro['grand_deplacement'] = grand_deplacement_data
        if mutation_data.get('hebergement_provisoire'):
            frais_pro['mutation_professionnelle'] = mutation_data
            
        # On ne touche pas aux autres clés (petit_deplacement, teletravail, etc.)
        print("Note : Les barèmes 'petit déplacement' et 'télétravail' ne sont pas sur cette page et n'ont pas été mis à jour.")

        with open(FICHIER_BAREMES, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
            
        print(f"✅ Le fichier '{FICHIER_BAREMES}' a été mis à jour avec succès.")

    except Exception as e:
        print(f"ERREUR : Le script a échoué. Raison : {e}")

if __name__ == "__main__":
    get_and_update_baremes_legisocial()