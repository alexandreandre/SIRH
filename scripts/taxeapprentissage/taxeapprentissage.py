# scripts/taxeapprentissage/taxeapprentissage.py

import json
import re
import sys
from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup

URL_URSSAF = "https://www.urssaf.fr/accueil/employeur/cotisations/liste-cotisations/taxe-apprentissage-csa.html"

# --- UTILITAIRES ---
def iso_now() -> str:
    """Retourne la date et l'heure actuelles au format ISO 8601 UTC."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def parse_taux(text: str) -> float | None:
    """Nettoie un texte (ex: "0,59 %") et le convertit en taux réel (0.0059)."""
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
def scrape_taxe_apprentissage_rates() -> dict | None:
    """
    Scrape les taux de la taxe d'apprentissage (part principale et solde).
    """
    try:
        print(f"Scraping de l'URL : {URL_URSSAF}...", file=sys.stderr)
        r = requests.get(URL_URSSAF, timeout=20, headers={
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
        })
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        
        rates = {}

        # --- 1. Extraction de la part principale ---
        h5_principale = soup.find('h5', string=re.compile("Part principale de la taxe d’apprentissage"))
        if not h5_principale:
            raise ValueError("Titre 'Part principale' introuvable.")
        
        article_principale = h5_principale.find_parent('article')
        list_items = article_principale.find('ul').find_all('li')
        
        taux_metropole_principale = parse_taux(list_items[0].get_text())
        taux_alsace_moselle_principale = parse_taux(list_items[1].get_text())
        
        rates["part_principale"] = {
            "taux_metropole": taux_metropole_principale,
            "taux_alsace_moselle": taux_alsace_moselle_principale
        }
        print(f"  - Taux Part Principale (Métropole) : {taux_metropole_principale*100:.2f}%", file=sys.stderr)
        print(f"  - Taux Part Principale (Alsace-Moselle) : {taux_alsace_moselle_principale*100:.2f}%", file=sys.stderr)

        # --- 2. Extraction du solde ---
        h5_solde = soup.find('h5', string=re.compile("Solde de la taxe d’apprentissage"))
        if not h5_solde:
            raise ValueError("Titre 'Solde' introuvable.")
            
        article_solde = h5_solde.find_parent('article')
        p_solde = article_solde.find('p')
        
        taux_metropole_solde = parse_taux(p_solde.get_text())
        # Le solde n'est pas dû en Alsace-Moselle, le taux est donc de 0.
        taux_alsace_moselle_solde = 0.0

        rates["solde"] = {
            "taux_metropole": taux_metropole_solde,
            "taux_alsace_moselle": taux_alsace_moselle_solde
        }
        print(f"  - Taux Solde (Métropole) : {taux_metropole_solde*100:.2f}%", file=sys.stderr)
        print(f"  - Taux Solde (Alsace-Moselle) : {taux_alsace_moselle_solde*100:.2f}%", file=sys.stderr)

        if not all([taux_metropole_principale, taux_alsace_moselle_principale, taux_metropole_solde is not None]):
            raise ValueError("Un ou plusieurs taux sont manquants.")

        return rates
        
    except Exception as e:
        print(f"ERREUR : Le scraping a échoué. Raison : {e}", file=sys.stderr)
        return None

# --- FONCTION PRINCIPALE ---
def main():
    """Orchestre le scraping et génère la sortie JSON pour l'orchestrateur."""
    rates_data = scrape_taxe_apprentissage_rates()
    
    if not rates_data:
        print("ERREUR CRITIQUE: Le scraping de la taxe d'apprentissage a échoué.", file=sys.stderr)
        sys.exit(1)

    # --- NOUVEAU : Calcul des totaux ---
    part_principale = rates_data.get("part_principale", {})
    solde = rates_data.get("solde", {})

    total_metropole = (part_principale.get("taux_metropole", 0.0) + 
                       solde.get("taux_metropole", 0.0))
    total_alsace_moselle = (part_principale.get("taux_alsace_moselle", 0.0) + 
                            solde.get("taux_alsace_moselle", 0.0))

    rates_data["total"] = {
        "taux_metropole": round(total_metropole, 6),
        "taux_alsace_moselle": round(total_alsace_moselle, 6)
    }
    # --- FIN DU NOUVEAU BLOC ---

    payload = {
        "id": "taxe_apprentissage",
        "type": "cotisation",
        "libelle": "Taxe d'Apprentissage",
        "sections": {
            "salarial": None,
            "part_principale": rates_data.get("part_principale"),
            "solde": rates_data.get("solde"),
            "total": rates_data.get("total") # Ajout du total
        },
        "meta": {
            "source": [{
                "url": URL_URSSAF,
                "label": "URSSAF - Taxe d'apprentissage",
                "date_doc": ""
            }],
            "scraped_at": iso_now(),
            "generator": "scripts/taxeapprentissage/taxeapprentissage.py",
            "method": "primary"
        }
    }
    
    print(json.dumps(payload, ensure_ascii=False))

if __name__ == "__main__":
    main()