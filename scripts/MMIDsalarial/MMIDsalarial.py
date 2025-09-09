# scripts/MMIDsalarial/MMIDsalarial.py

import json
import re
import sys
from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup

URL_URSSAF = "https://www.urssaf.fr/accueil/outils-documentation/taux-baremes/taux-cotisations-secteur-prive.html"

# --- FONCTIONS UTILITAIRES ---

def iso_now() -> str:
    """Retourne la date et l'heure actuelles au format ISO 8601 UTC."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def get_taux_alsace_moselle() -> float | None:
    """
    Scrape le site de l'URSSAF pour trouver le taux de la cotisation salariale
    spécifique à l'Alsace-Moselle.
    """
    try:
        print(f"Scraping de l'URL : {URL_URSSAF}...", file=sys.stderr)
        r = requests.get(URL_URSSAF, timeout=20, headers={
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
        })
        r.raise_for_status()

        soup = BeautifulSoup(r.text, "html.parser")
        
        # Cible la section des cotisations salariales
        articles = soup.find_all('article')
        salarie_section_text = ""
        for article in articles:
            h2 = article.find('h2', class_='h4-like')
            if h2 and 'taux de cotisations salarié' in h2.get_text(strip=True).lower():
                salarie_section_text = article.get_text(" ", strip=True)
                break

        if not salarie_section_text:
            raise ValueError("Section 'Taux de cotisations salarié' introuvable.")
        
        # Extrait le taux avec une expression régulière
        motif = r"Cotisation salariale maladie supplémentaire.*?Moselle\s*([0-9,]+)\s*%"
        m = re.search(motif, salarie_section_text, flags=re.IGNORECASE)
        
        if not m:
            raise ValueError("Motif du taux Alsace-Moselle introuvable sur la page.")
        
        taux_str = m.group(1).replace(",", ".")
        # Le taux est déjà en pourcentage, on le convertit en décimal
        taux = round(float(taux_str) / 100.0, 5) 
        
        print(f"Taux Alsace-Moselle trouvé : {taux*100:.2f}%", file=sys.stderr)
        return taux
        
    except Exception as e:
        print(f"ERREUR : Le scraping du taux Alsace-Moselle a échoué. Raison : {e}", file=sys.stderr)
        return None

# --- FONCTION PRINCIPALE ---

def main():
    """
    Orchestre le scraping et génère la sortie JSON pour l'orchestrateur.
    """
    taux = get_taux_alsace_moselle()

    if taux is None:
        print("ERREUR CRITIQUE: Le taux n'a pas pu être récupéré.", file=sys.stderr)
        sys.exit(1)

    # Assemblage du payload final conforme à la structure de l'orchestrateur
    payload = {
        "id": "maladie_alsace_moselle",
        "type": "taux_cotisation_specifique",
        "libelle": "Taux de cotisation salariale maladie - Alsace-Moselle",
        "sections": {
            "alsace_moselle": {
                "taux_salarial": taux
            }
        },
        "meta": {
            "source": [{
                "url": URL_URSSAF,
                "label": "URSSAF - Taux de cotisations secteur privé",
                "date_doc": ""
            }],
            "scraped_at": iso_now(),
            "generator": "scripts/MMIDsalarial/MMIDsalarial.py",
            "method": "primary"
        }
    }

    # Impression du JSON final sur la sortie standard
    print(json.dumps(payload, ensure_ascii=False))


if __name__ == "__main__":
    main()