# scripts/CFP/CFP_LegiSocial.py

import json
import re
import sys
from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup

URL_LEGISOCIAL = "https://www.legisocial.fr/reperes-sociaux/taxe-formation-professionnelle-continue-2025.html"

# --- UTILITAIRES ---
def iso_now() -> str:
    """Retourne la date et l'heure actuelles au format ISO 8601 UTC."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def parse_taux(text: str) -> float | None:
    """Nettoie un texte (ex: "0,55%") et le convertit en taux réel (0.0055)."""
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
def scrape_cfp_rates_legisocial() -> dict | None:
    """
    Scrape le site de LegiSocial pour les taux de la Contribution à la Formation Professionnelle (CFP).
    """
    try:
        print(f"Scraping de l'URL : {URL_LEGISOCIAL}...", file=sys.stderr)
        r = requests.get(URL_LEGISOCIAL, timeout=20, headers={
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
        })
        r.raise_for_status()

        soup = BeautifulSoup(r.text, "html.parser")
        
        taux_moins_11 = None
        taux_11_et_plus = None

        # --- NOUVELLE LOGIQUE DE CIBLAGE PLUS SOUPLE ---
        # 1. On cherche une balise qui contient le texte "Effectif" pour trouver le tableau
        header_tag = soup.find(lambda tag: tag.name in ['p', 'td', 'th'] and 'Effectif' in tag.get_text(strip=True))
        if not header_tag:
            raise ValueError("Impossible de trouver l'en-tête de la table des taux ('Effectif').")
        
        # 2. On remonte jusqu'à la balise <table> parente
        table = header_tag.find_parent('table')
        if not table:
             raise ValueError("Impossible de trouver la balise <table> parente de l'en-tête.")

        # 3. On parcourt les lignes de ce tableau
        for row in table.find_all('tr'):
            cells = row.find_all('td')
            if len(cells) == 2:
                label = cells[0].get_text(strip=True)
                valeur_text = cells[1].get_text(strip=True)

                if '< 11' in label:
                    taux_moins_11 = parse_taux(valeur_text)
                elif '≥ 11' in label:
                    taux_11_et_plus = parse_taux(valeur_text)

        if taux_moins_11 is None or taux_11_et_plus is None:
            raise ValueError("Impossible de trouver les deux taux CFP sur la page.")

        print(f"  - Taux (< 11 salariés) trouvé : {taux_moins_11*100:.2f}%", file=sys.stderr)
        print(f"  - Taux (11+ salariés) trouvé : {taux_11_et_plus*100:.2f}%", file=sys.stderr)
        
        return {
            "patronal_moins_11": taux_moins_11,
            "patronal_11_et_plus": taux_11_et_plus
        }
        
    except Exception as e:
        print(f"ERREUR : Le scraping a échoué. Raison : {e}", file=sys.stderr)
        return None

# --- FONCTION PRINCIPALE ---
def main():
    """Orchestre le scraping et génère la sortie JSON pour l'orchestrateur."""
    rates_data = scrape_cfp_rates_legisocial()
    
    if not rates_data:
        print("ERREUR CRITIQUE: Le scraping des taux de CFP via LegiSocial a échoué.", file=sys.stderr)
        sys.exit(1)

    payload = {
        "id": "cfp",
        "type": "cotisation",
        "libelle": "Contribution à la Formation Professionnelle (CFP)",
        "sections": {
            "salarial": None,
            "patronal_moins_11": rates_data.get("patronal_moins_11"),
            "patronal_11_et_plus": rates_data.get("patronal_11_et_plus")
        },
        "meta": {
            "source": [{
                "url": URL_LEGISOCIAL,
                "label": "LegiSocial - Taxe Formation Professionnelle",
                "date_doc": ""
            }],
            "scraped_at": iso_now(),
            "generator": "scripts/CFP/CFP_LegiSocial.py",
            "method": "secondary"
        }
    }
    
    print(json.dumps(payload, ensure_ascii=False))

if __name__ == "__main__":
    main()