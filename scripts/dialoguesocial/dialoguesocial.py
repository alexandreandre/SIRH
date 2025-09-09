# scripts/dialoguesocial/dialoguesocial.py

import json
import re
import sys
from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup

URL_URSSAF = "https://www.urssaf.fr/accueil/outils-documentation/taux-baremes/taux-cotisations-secteur-prive.html"

# --- UTILITAIRES ---
def iso_now() -> str:
    """Retourne la date et l'heure actuelles au format ISO 8601 UTC."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def parse_taux(text: str) -> float | None:
    """Nettoie un texte (ex: "0,016 %") et le convertit en taux réel (0.00016)."""
    if not text:
        return None
    try:
        cleaned_text = text.replace(',', '.').replace('%', '').replace('\xa0', '').strip()
        numeric_part = re.search(r"([0-9]+\.?[0-9]*)", cleaned_text)
        if not numeric_part:
            return None
        taux = float(numeric_part.group(1)) / 100.0
        return round(taux, 6)
    except (ValueError, AttributeError):
        return None

# --- SCRAPER ---
def scrape_dialogue_social_rate() -> float | None:
    """
    Scrape le site de l'URSSAF pour trouver le taux de la contribution au dialogue social.
    """
    try:
        print(f"Scraping de l'URL : {URL_URSSAF}...", file=sys.stderr)
        r = requests.get(URL_URSSAF, timeout=20, headers={
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
        })
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        
        # --- LOGIQUE DE CIBLAGE DÉFINITIVE ---
        target_row = None
        # 1. On parcourt toutes les lignes <tr> de la page
        for row in soup.find_all('tr'):
            # 2. Pour chaque ligne, on cherche une cellule d'en-tête <th>
            header_cell = row.find('th')
            # 3. Si l'en-tête existe et contient notre texte, c'est la bonne ligne
            if header_cell and "Contribution au dialogue social" in header_cell.get_text(strip=True):
                target_row = row
                break
        
        if not target_row:
            raise ValueError("Impossible de trouver la ligne <tr> contenant l'en-tête 'Contribution au dialogue social'.")
        
        # 4. La valeur se trouve dans la cellule <td> de cette ligne
        value_cell = target_row.find('td')
        if not value_cell:
            raise ValueError("Cellule de valeur <td> introuvable dans la ligne.")
            
        rate = parse_taux(value_cell.get_text())
        if rate is None:
            raise ValueError("Impossible de parser le taux de la contribution.")

        print(f"  - Taux trouvé : {rate*100:.3f}%", file=sys.stderr)
        return rate
        
    except Exception as e:
        print(f"ERREUR : Le scraping a échoué. Raison : {e}", file=sys.stderr)
        return None

# --- FONCTION PRINCIPALE ---
def main():
    """Orchestre le scraping et génère la sortie JSON pour l'orchestrateur."""
    rate_data = scrape_dialogue_social_rate()
    
    if rate_data is None:
        print("ERREUR CRITIQUE: Le scraping du taux de dialogue social a échoué.", file=sys.stderr)
        sys.exit(1)

    payload = {
        "id": "dialogue_social",
        "type": "cotisation",
        "libelle": "Contribution au dialogue social",
        "sections": {
            "salarial": None,
            "patronal": rate_data
        },
        "meta": {
            "source": [{
                "url": URL_URSSAF,
                "label": "URSSAF - Taux de cotisations secteur privé",
                "date_doc": ""
            }],
            "scraped_at": iso_now(),
            "generator": "scripts/dialoguesocial/dialoguesocial.py",
            "method": "primary"
        }
    }
    
    print(json.dumps(payload, ensure_ascii=False))

if __name__ == "__main__":
    main()