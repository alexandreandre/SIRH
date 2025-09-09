# scripts/Avantages_LegiSocial.py

import json
import re
import requests
from bs4 import BeautifulSoup

# --- Fichiers et URL cibles ---
FICHIER_ENTREPRISE = 'config/parametres_entreprise.json'
URL_REPAS = "https://www.legisocial.fr/reperes-sociaux/avantage-en-nature-repas-2025.html"
URL_LOGEMENT = "https://www.legisocial.fr/reperes-sociaux/avantage-en-nature-logement-2025.html"

def parse_valeur_numerique(text: str) -> float:
    """Nettoie et convertit un texte en nombre (float)."""
    if not text: return 0.0
    # Remplace les points (séparateurs de milliers) et les espaces, puis la virgule par un point décimal
    cleaned = text.replace('.', '').replace('€', '').replace('\xa0', '').replace(' ', '').replace(',', '.')
    match = re.search(r"([0-9]+\.?[0-9]*)", cleaned)
    return float(match.group(1)) if match else 0.0

def scrape_repas_data() -> dict | None:
    """Scrape la page des avantages repas et titre-restaurant."""
    print(f"Scraping de l'URL Repas : {URL_REPAS}...")
    response = requests.get(URL_REPAS, timeout=20, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.0.0 Safari/537.36"
    })
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")

    table = soup.find('table')
    if not table:
        raise ValueError("Table des avantages repas introuvable.")
    
    data = {}
    for row in table.find_all('tr'):
        cells = row.find_all('td')
        if len(cells) == 2:
            libelle = cells[0].get_text().lower()
            valeur = parse_valeur_numerique(cells[1].get_text())
            
            if "avantage en nature repas (1 repas)" in libelle and "hcr" not in libelle:
                data['repas_valeur_forfaitaire'] = valeur
            elif "participation patronale maximum sur tickets restaurant" in libelle:
                data['titre_restaurant_exoneration_max_patronale'] = valeur
    
    if 'repas_valeur_forfaitaire' in data and 'titre_restaurant_exoneration_max_patronale' in data:
        print(f"  - Données Repas/Titre-restaurant trouvées : {data}")
        return data
    
    raise ValueError("Impossible de trouver toutes les données sur la page Repas.")

def scrape_logement_data() -> list | None:
    """Scrape la page du barème logement."""
    print(f"Scraping de l'URL Logement : {URL_LOGEMENT}...")
    response = requests.get(URL_LOGEMENT, timeout=20, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.0.0 Safari/537.36"
    })
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")

    # --- LOGIQUE DE RECHERCHE CORRIGÉE ---
    # On parcourt tous les h3 pour trouver le bon titre de manière flexible
    header = None
    for h3 in soup.find_all('h3'):
        if 'méthode de l’évaluation forfaitaire' in h3.get_text().lower():
            header = h3
            break
            
    if not header:
        raise ValueError("Titre de la section 'Évaluation forfaitaire' introuvable.")
        
    table = header.find_next('table')
    if not table:
        raise ValueError("Table du barème logement introuvable.")
        
    rows = table.find('tbody').find_all('tr')
    if len(rows) != 3:
        raise ValueError("La structure de la table logement n'est pas celle attendue (3 lignes).")

    tranches_remu_cells = rows[0].find_all('td')[1:]
    valeurs_1_piece_cells = rows[1].find_all('td')[1:]
    valeurs_par_piece_cells = rows[2].find_all('td')[1:]

    bareme = []
    # La dernière valeur numérique dans la cellule de tranche est le plafond
    for i in range(len(tranches_remu_cells)):
        remu_text = tranches_remu_cells[i].get_text(separator=' ').strip()
        all_numbers_str = re.findall(r'[0-9\.]+,[0-9]+', remu_text.replace('.', ''))
        
        remu_max = float('inf') # Pour la dernière tranche "À partir de..."
        if all_numbers_str:
            remu_max = parse_valeur_numerique(all_numbers_str[-1])
        
        bareme.append({
            "remuneration_max": remu_max,
            "valeur_1_piece": parse_valeur_numerique(valeurs_1_piece_cells[i].get_text()),
            "valeur_par_piece": parse_valeur_numerique(valeurs_par_piece_cells[i].get_text())
        })

    if bareme:
        print(f"  - Barème logement complet trouvé ({len(bareme)} tranches).")
        return bareme
        
    raise ValueError("Impossible de construire le barème logement.")

def get_and_update_avantages():
    """Orchestre le scraping des deux pages et met à jour la configuration."""
    try:
        repas_data = scrape_repas_data()
        logement_data = scrape_logement_data()

        if not repas_data or not logement_data:
            raise ValueError("Une des sources de données n'a pu être scrapée.")

        final_data = {
            "repas_valeur_forfaitaire": repas_data['repas_valeur_forfaitaire'],
            "titre_restaurant_exoneration_max_patronale": repas_data['titre_restaurant_exoneration_max_patronale'],
            "logement_bareme_forfaitaire": logement_data
        }

        with open(FICHIER_ENTREPRISE, 'r', encoding='utf-8') as f:
            config = json.load(f)
            
        avantages = config['PARAMETRES_ENTREPRISE'].setdefault('avantages_en_nature', {})
        print("\nMise à jour du fichier de configuration...")
        avantages.update(final_data)

        with open(FICHIER_ENTREPRISE, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
            
        print(f"✅ Le fichier '{FICHIER_ENTREPRISE}' a été mis à jour avec succès.")

    except Exception as e:
        print(f"ERREUR : Le script a échoué. Raison : {e}")

if __name__ == "__main__":
    get_and_update_avantages()