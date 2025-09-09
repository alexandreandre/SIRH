# scripts/dialoguesocial/dialoguesocial_LegiSocial.py

import json
import re
import sys
from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup

URL_LEGISOCIAL = "https://www.legisocial.fr/reperes-sociaux/taux-cotisations-sociales-urssaf-2025.html"

# --- UTILITAIRES ---
def iso_now() -> str:
    """Retourne la date et l'heure actuelles au format ISO 8601 UTC."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def parse_taux(text: str) -> float | None:
    """Nettoie un texte (ex: "0,016 %") et le convertit en taux réel (0.00016)."""
    if not text:
        return None
    try:
        cleaned_text = text.replace(',', '.').replace('%', '').strip()
        numeric_part = re.search(r"([0-9]+\.?[0-9]*)", cleaned_text)
        if not numeric_part:
            return None
        taux = float(numeric_part.group(1)) / 100.0
        return round(taux, 6)
    except (ValueError, AttributeError):
        return None

# --- SCRAPER ---
def scrape_dialogue_social_rate_legisocial() -> float | None:
    """
    Scrape LegiSocial pour trouver le taux de la contribution au dialogue social.
    """
    try:
        print(f"Scraping de l'URL : {URL_LEGISOCIAL}...", file=sys.stderr)
        r = requests.get(URL_LEGISOCIAL, timeout=20, headers={
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
        })
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        
        # On trouve une balise contenant le texte pour s'ancrer
        anchor_tag = soup.find(lambda tag: tag.name in ['p', 'td'] and "Contribution au dialogue social" in tag.get_text(strip=True))
        if not anchor_tag:
            raise ValueError("Ligne 'Contribution au dialogue social' introuvable.")
        
        # On remonte à la ligne <tr> parente
        target_row = anchor_tag.find_parent('tr')
        if not target_row:
            raise ValueError("Ligne <tr> parente introuvable.")
            
        cells = target_row.find_all('td')
        if len(cells) < 5:
            raise ValueError("La ligne ne contient pas les 5 colonnes attendues.")
        
        # Le taux patronal est dans la 5ème cellule (index 4)
        rate = parse_taux(cells[4].get_text())
        if rate is None:
            raise ValueError("Impossible de parser le taux dans la cellule cible.")

        print(f"  - Taux trouvé : {rate*100:.3f}%", file=sys.stderr)
        return rate
        
    except Exception as e:
        print(f"ERREUR : Le scraping a échoué. Raison : {e}", file=sys.stderr)
        return None

# --- FONCTION PRINCIPALE ---
def main():
    """Orchestre le scraping et génère la sortie JSON pour l'orchestrateur."""
    rate_data = scrape_dialogue_social_rate_legisocial()
    
    if rate_data is None:
        print("ERREUR CRITIQUE: Le scraping du taux via LegiSocial a échoué.", file=sys.stderr)
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
                "url": URL_LEGISOCIAL,
                "label": "LegiSocial - Taux de cotisations sociales",
                "date_doc": ""
            }],
            "scraped_at": iso_now(),
            "generator": "scripts/dialoguesocial/dialoguesocial_LegiSocial.py",
            "method": "secondary"
        }
    }
    
    print(json.dumps(payload, ensure_ascii=False))

if __name__ == "__main__":
    main()