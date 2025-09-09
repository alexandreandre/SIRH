# scripts/vieillessesalarial/vieillessesalarial.py

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

# --- SCRAPER ---
def get_taux_vieillesse_salarial() -> dict | None:
    """
    Scrape le site de l'URSSAF pour trouver les taux de l'assurance vieillesse salariale.
    """
    try:
        print(f"Scraping de l'URL : {URL_URSSAF}...", file=sys.stderr)
        r = requests.get(URL_URSSAF, timeout=20, headers={
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
        })
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        
        # Isoler la section "salarié"
        articles = soup.find_all('article')
        salarie_section_text = ""
        for article in articles:
            h2 = article.find('h2', class_='h4-like')
            if h2 and 'taux de cotisations salarié' in h2.get_text(strip=True).lower():
                salarie_section_text = article.get_text(" ", strip=True)
                break

        if not salarie_section_text:
            raise ValueError("La section 'Taux de cotisations salarié' est introuvable.")

        # Appliquer la recherche regex sur le texte de la section
        motif = r"Assurance vieillesse\s*([0-9,]+)\s*%\s*sur la totalité et\s*([0-9,]+)\s*%\s*dans la limite du plafond"
        m = re.search(motif, salarie_section_text, flags=re.IGNORECASE)
        
        if not m:
            raise ValueError("Motif des taux d'assurance vieillesse salariale introuvable.")
        
        taux_deplafonne_str = m.group(1).replace(",", ".")
        taux_plafonne_str = m.group(2).replace(",", ".")
        
        taux_deplafonne = round(float(taux_deplafonne_str) / 100.0, 5)
        taux_plafonne = round(float(taux_plafonne_str) / 100.0, 5)
        
        print(f"  - Taux vieillesse déplafonné (salarial) trouvé : {taux_deplafonne*100:.2f}%", file=sys.stderr)
        print(f"  - Taux vieillesse plafonné (salarial) trouvé   : {taux_plafonne*100:.2f}%", file=sys.stderr)
        
        return {"deplafonne": taux_deplafonne, "plafonne": taux_plafonne}
        
    except Exception as e:
        print(f"ERREUR : Le scraping a échoué. Raison : {e}", file=sys.stderr)
        return None

# --- FONCTION PRINCIPALE ---
def main():
    """Orchestre le scraping et génère la sortie JSON pour l'orchestrateur."""
    taux_data = get_taux_vieillesse_salarial()
    
    if not taux_data:
        print("ERREUR CRITIQUE: Le scraping des taux de vieillesse salariaux a échoué.", file=sys.stderr)
        sys.exit(1)

    payload = {
        "id": "assurance_vieillesse_salarial",
        "type": "taux_cotisation",
        "libelle": "Taux de cotisation salariale - Assurance Vieillesse",
        "sections": taux_data,
        "meta": {
            "source": [{
                "url": URL_URSSAF,
                "label": "URSSAF - Taux de cotisations secteur privé",
                "date_doc": ""
            }],
            "scraped_at": iso_now(),
            "generator": "scripts/vieillessesalarial/vieillessesalarial.py",
            "method": "primary"
        }
    }
    
    print(json.dumps(payload, ensure_ascii=False))

if __name__ == "__main__":
    main()