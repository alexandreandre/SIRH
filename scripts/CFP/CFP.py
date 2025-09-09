# scripts/CFP/CFP.py

import json
import re
import sys
from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup

URL_URSSAF = "https://www.urssaf.fr/accueil/employeur/cotisations/liste-cotisations/formation-professionnelle.html"

# --- UTILITAIRES ---
def iso_now() -> str:
    """Retourne la date et l'heure actuelles au format ISO 8601 UTC."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def parse_taux(text: str) -> float | None:
    """Nettoie un texte (ex: "0,55 %") et le convertit en taux réel (0.0055)."""
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
def scrape_cfp_rates() -> dict | None:
    """
    Scrape le site de l'URSSAF pour trouver les taux de la Contribution à la Formation Professionnelle (CFP).
    """
    try:
        print(f"Scraping de l'URL : {URL_URSSAF}...", file=sys.stderr)
        r = requests.get(URL_URSSAF, timeout=20, headers={
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
        })
        r.raise_for_status()

        soup = BeautifulSoup(r.text, "html.parser")
        
        # --- NOUVELLE LOGIQUE DE CIBLAGE ---
        # 1. Trouver le paragraphe d'introduction qui sert d'ancre
        anchor_p = soup.find('p', string=re.compile(r"Le taux de la contribution à la formation professionnelle varie"))
        if not anchor_p:
            raise ValueError("Paragraphe d'ancre introuvable sur la page. La structure a peut-être changé.")
        
        # 2. Le paragraphe contenant les taux est le suivant
        target_p = anchor_p.find_next_sibling('p')
        if not target_p:
            raise ValueError("Paragraphe contenant les taux introuvable après l'ancre.")
        
        page_text = target_p.get_text(" ", strip=True)

        # 3. Appliquer les regex sur ce texte ciblé
        motif_moins_11 = re.search(r"([0-9,]+\s*\%)\s*si vous employez\s*moins de 11\s*salariés", page_text, re.IGNORECASE)
        motif_11_et_plus = re.search(r"([0-9,]+\s*\%)\s*si vous employez\s*11\s*salariés et plus", page_text, re.IGNORECASE)

        taux_moins_11 = parse_taux(motif_moins_11.group(1)) if motif_moins_11 else None
        taux_11_et_plus = parse_taux(motif_11_et_plus.group(1)) if motif_11_et_plus else None
        
        if taux_moins_11 is None or taux_11_et_plus is None:
            raise ValueError("Impossible de trouver les deux taux de formation professionnelle dans le paragraphe cible.")

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
    rates_data = scrape_cfp_rates()
    
    if not rates_data:
        print("ERREUR CRITIQUE: Le scraping des taux de CFP a échoué.", file=sys.stderr)
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
                "url": URL_URSSAF,
                "label": "URSSAF - Contribution à la formation professionnelle",
                "date_doc": ""
            }],
            "scraped_at": iso_now(),
            "generator": "scripts/CFP/CFP.py",
            "method": "primary"
        }
    }
    
    print(json.dumps(payload, ensure_ascii=False))

if __name__ == "__main__":
    main()