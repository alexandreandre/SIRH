# scripts/SMIC/SMIC.py

import json
import re
import sys
from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup

URL_URSSAF = "https://www.urssaf.fr/accueil/outils-documentation/taux-baremes/montant-smic.html"

# --- UTILITAIRES ---
def iso_now() -> str:
    """Retourne la date et l'heure actuelles au format ISO 8601 UTC."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def parse_valeur_numerique(text: str) -> float:
    """Nettoie et convertit un texte contenant une valeur monétaire en float."""
    if not text: return 0.0
    cleaned_text = text.replace(',', '.').replace('\xa0', '').replace('€', '').strip()
    match = re.search(r"([0-9]+\.?[0-9]*)", cleaned_text)
    if match:
        return float(match.group(1))
    return 0.0

# --- SCRAPER ---
def get_smic_horaire_par_cas(soup, section_id: str, nom_cas: str) -> float:
    """Fonction générique pour scraper le SMIC horaire d'une section donnée."""
    section = soup.find('div', id=section_id)
    if not section:
        raise ValueError(f"Section '{nom_cas}' (ID: {section_id}) introuvable.")
    
    table_rows = section.find_all('tr')
    for row in table_rows:
        header_cell = row.find('th')
        if header_cell and 'Smic horaire brut' in header_cell.get_text(strip=True):
            value_cell = row.find('td')
            if not value_cell:
                raise ValueError(f"Cellule de valeur manquante pour le SMIC horaire dans '{nom_cas}'.")
            
            valeur_smic = parse_valeur_numerique(value_cell.get_text())
            print(f"  - SMIC horaire brut trouvé ({nom_cas}): {valeur_smic} €", file=sys.stderr)
            return valeur_smic
            
    raise ValueError(f"Ligne 'Smic horaire brut' introuvable dans la section '{nom_cas}'.")

def get_tous_les_smic() -> dict | None:
    """
    Scrape le site de l'URSSAF pour trouver tous les montants du SMIC horaire.
    """
    try:
        print(f"Scraping de l'URL : {URL_URSSAF}...", file=sys.stderr)
        r = requests.get(URL_URSSAF, timeout=20, headers={
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
        })
        r.raise_for_status()

        soup = BeautifulSoup(r.text, "html.parser")
        
        # L'année cible peut être mise à jour ici si nécessaire
        current_year = datetime.now().year
        
        smic_valeurs = {
            "cas_general": get_smic_horaire_par_cas(soup, f'Cas-general-{current_year}', 'Cas général'),
            "jeune_17_ans": get_smic_horaire_par_cas(soup, f'salaries-entre-17-18-{current_year}', '17 ans'),
            "jeune_moins_17_ans": get_smic_horaire_par_cas(soup, f'salaries-moins-17-{current_year}', 'Moins de 17 ans')
        }
        
        return smic_valeurs

    except Exception as e:
        print(f"ERREUR : Le scraping a échoué. Raison : {e}", file=sys.stderr)
        return None

# --- FONCTION PRINCIPALE ---
def main():
    """Orchestre le scraping et génère la sortie JSON pour l'orchestrateur."""
    smic_data = get_tous_les_smic()
    
    if not smic_data:
        print("ERREUR CRITIQUE: Le scraping du SMIC a échoué ou n'a retourné aucune donnée.", file=sys.stderr)
        sys.exit(1)

    payload = {
        "id": "smic_horaire",
        "type": "bareme_horaire",
        "libelle": "Salaire Minimum Interprofessionnel de Croissance (SMIC) - Taux horaire",
        "sections": smic_data,
        "meta": {
            "source": [{
                "url": URL_URSSAF,
                "label": "URSSAF - Montant du Smic",
                "date_doc": ""
            }],
            "scraped_at": iso_now(),
            "generator": "scripts/SMIC/SMIC.py",
            "method": "primary"
        }
    }
    
    # Impression du JSON final sur la sortie standard
    print(json.dumps(payload, ensure_ascii=False))

if __name__ == "__main__":
    main()