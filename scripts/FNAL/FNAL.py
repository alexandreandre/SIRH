# scripts/FNAL/FNAL.py
import json
import os
import re
import sys
from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup

URL_URSSAF = "https://www.urssaf.fr/accueil/outils-documentation/taux-baremes/taux-cotisations-secteur-prive.html"

def iso_now() -> str:
    """Retourne la date et l'heure actuelles au format ISO 8601 UTC."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def _parse_percent_to_rate(text: str) -> float | None:
    """Extrait un pourcentage d'une chaîne et le convertit en taux décimal."""
    if not text:
        return None
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*%", text)
    if not m:
        return None
    return round(float(m.group(1).replace(",", ".")) / 100.0, 6)

def _fetch_page(url: str) -> BeautifulSoup:
    """Récupère et parse le contenu HTML d'une URL."""
    r = requests.get(
        url,
        timeout=25,
        headers={
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
        },
    )
    r.raise_for_status()
    return BeautifulSoup(r.text, "html.parser")

def _find_employeur_section(soup: BeautifulSoup):
    """Trouve la section HTML contenant les taux employeur."""
    for article in soup.find_all("article"):
        h2 = article.find("h2", class_="h4-like")
        if h2 and "taux de cotisations employeur" in h2.get_text(strip=True).lower():
            return article
    return None

def scrape_fnal_rates() -> dict[str, float | None]:
    """
    Scrape et retourne les deux taux FNAL (< 50 et 50 et plus).
    """
    print(f"Scraping de l'URL : {URL_URSSAF}...", file=sys.stderr)
    try:
        soup = _fetch_page(URL_URSSAF)
        section = _find_employeur_section(soup)
        if not section:
            raise ValueError("Section 'Taux de cotisations employeur' introuvable.")

        rows = section.find_all("tr", class_="table_custom__tbody")
        taux_moins_50, taux_50_et_plus = None, None

        # Expressions régulières pour cibler les bonnes lignes
        pat_moins_50 = re.compile(r"Fnal\s*\(.*moins\s+de\s+50\s+salari", re.IGNORECASE)
        pat_50_et_plus = re.compile(r"Fnal\s*\(.*50\s+salari[éê]s\s+et\s+plus", re.IGNORECASE)

        for row in rows:
            th = row.find("th")
            if not th: continue
            
            label = th.get_text(" ", strip=True)
            td = row.find("td")
            if not td: continue

            rate = _parse_percent_to_rate(td.get_text(" ", strip=True))
            if rate is None: continue

            if pat_moins_50.search(label):
                taux_moins_50 = rate
            elif pat_50_et_plus.search(label):
                taux_50_et_plus = rate
        
        print(f"  - Taux FNAL (< 50 salariés) trouvé : {taux_moins_50}", file=sys.stderr)
        print(f"  - Taux FNAL (50+ salariés) trouvé : {taux_50_et_plus}", file=sys.stderr)

        return {"patronal_moins_50": taux_moins_50, "patronal_50_et_plus": taux_50_et_plus}
    except Exception as e:
        print(f"ERREUR : Le scraping a échoué. Raison : {e}", file=sys.stderr)
        return {"patronal_moins_50": None, "patronal_50_et_plus": None}

def main() -> None:
    """
    Orchestre le scraping et génère la sortie JSON pour l'orchestrateur.
    """
    rates = scrape_fnal_rates()

    # Vérification que les deux taux ont bien été trouvés
    if rates.get("patronal_moins_50") is None or rates.get("patronal_50_et_plus") is None:
        print("ERREUR CRITIQUE: Un ou plusieurs taux FNAL n'ont pas pu être scrapés.", file=sys.stderr)
        sys.exit(1)

    payload = {
        "id": "fnal",
        "type": "cotisation",
        "libelle": "Fonds National d’Aide au Logement (FNAL)",
        "sections": {
            "salarial": None, # FNAL est une cotisation exclusivement patronale
            "patronal_moins_50": rates["patronal_moins_50"],
            "patronal_50_et_plus": rates["patronal_50_et_plus"]
        },
        "meta": {
            "source": [{"url": URL_URSSAF, "label": "URSSAF — Taux secteur privé", "date_doc": ""}],
            "scraped_at": iso_now(),
            "generator": "scripts/FNAL/FNAL.py",
            "method": "primary",
        },
    }
    
    # Sortie JSON stricte pour l'orchestrateur
    print(json.dumps(payload, ensure_ascii=False))

if __name__ == "__main__":
    main()