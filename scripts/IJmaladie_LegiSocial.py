# scripts/IJmaladie_LegiSocial.py

import json
import re
import requests
from bs4 import BeautifulSoup
from datetime import datetime

# --- Fichiers et URL cibles ---
FICHIER_BAREMES = 'config/baremes.json'
URL_LEGISOCIAL = "https://www.legisocial.fr/reperes-sociaux/indemnites-journalieres-de-securite-sociale-ijss-2025.html"

def parse_valeur_numerique(text: str) -> float:
    """Nettoie et convertit un texte en nombre (float)."""
    if not text: return 0.0
    cleaned = text.replace('€', '').replace('\xa0', '').replace('\u202f', '').replace(' ', '').replace(',', '.')
    match = re.search(r"([0-9]+\.?[0-9]*)", cleaned)
    return float(match.group(1)) if match else 0.0

def get_all_plafonds_ij_legisocial() -> dict | None:
    """
    Scrape LegiSocial et retourne:
      - maladie : 2e valeur rencontrée
      - maternite_paternite : 1re valeur rencontrée
      - at_mp : 1re valeur rencontrée
      - at_mp_majoree : 1re valeur rencontrée
    """
    try:
        print(f"Scraping de l'URL : {URL_LEGISOCIAL}...")
        response = requests.get(URL_LEGISOCIAL, timeout=20, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.0.0 Safari/537.36"
        })
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")

        plafonds = {}
        maladie_hits = 0  # Compteur pour IJ Maladie

        for header in soup.find_all('h3'):
            header_text = header.get_text().lower()
            table = header.find_next('table')
            if not table:
                continue

            # --- IJ Maladie: prendre la 2e valeur uniquement ---
            if 'arrêt de travail maladie' in header_text:
                valeur_cell = table.find('mark')
                if valeur_cell:
                    valeur_maladie = parse_valeur_numerique(valeur_cell.get_text())
                    maladie_hits += 1
                    print(f"  - Plafond IJ Maladie trouvé : {valeur_maladie} €")
                    if maladie_hits == 2 and 'maladie' not in plafonds:
                        plafonds['maladie'] = valeur_maladie
                        print("    -> 2e valeur maladie retenue")

            # --- IJ Maternité/Paternité: prendre la 1re valeur uniquement ---
            elif 'congé de maternité' in header_text and 'maternite_paternite' not in plafonds:
                row = table.find(lambda tag: tag.name == 'td' and 'pour tous les assurés' in tag.get_text(strip=True).lower())
                if row:
                    parent_row = row.find_parent('tr')
                    cells = parent_row.find_all('td')
                    if len(cells) >= 2:
                        valeur = parse_valeur_numerique(cells[1].get_text())
                        plafonds['maternite_paternite'] = valeur
                        print(f"  - Plafond IJ Maternité/Paternité trouvé : {valeur} € (1re valeur retenue)")

            # --- IJ AT/MP: prendre les 1res occurrences uniquement ---
            elif 'accident du travail' in header_text:
                tbody = table.find('tbody') or table
                for row in tbody.find_all('tr'):
                    libelle = row.get_text().lower()
                    cells = row.find_all('td')
                    valeur_cell = next((cell for cell in cells if '€' in cell.get_text()), None)
                    if not valeur_cell:
                        continue
                    valeur = parse_valeur_numerique(valeur_cell.get_text())

                    if "jusqu'au 28" in libelle and 'at_mp' not in plafonds:
                        plafonds['at_mp'] = valeur
                        print(f"  - Plafond IJ AT/MP trouvé : {valeur} € (1re valeur retenue)")
                    elif "partir du 29" in libelle and 'at_mp_majoree' not in plafonds:
                        plafonds['at_mp_majoree'] = valeur
                        print(f"  - Plafond IJ AT/MP majorée trouvé : {valeur} € (1re valeur retenue)")

        if set(plafonds.keys()) != {'maladie', 'maternite_paternite', 'at_mp', 'at_mp_majoree'}:
            raise ValueError(f"Toutes les indemnités n'ont pas été trouvées. Trouvées : {plafonds}")

        return plafonds

    except Exception as e:
        print(f"ERREUR : Le scraping a échoué. Raison : {e}")
        return None

def update_config_file(nouveaux_plafonds: dict):
    try:
        with open(FICHIER_BAREMES, 'r', encoding='utf-8') as f:
            config = json.load(f)

        ij_config = config.setdefault('SECURITE_SOCIALE_2025', {}).setdefault('plafonds_indemnites_journalieres', {})
        print("\nMise à jour du fichier de configuration...")
        ij_config.update(nouveaux_plafonds)

        with open(FICHIER_BAREMES, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)

        print(f"✅ Le fichier '{FICHIER_BAREMES}' a été mis à jour avec succès.")

    except Exception as e:
        print(f"\nERREUR : Une erreur est survenue lors de la mise à jour : {e}")

if __name__ == "__main__":
    valeurs = get_all_plafonds_ij_legisocial()
    if valeurs is not None:
        update_config_file(valeurs)
