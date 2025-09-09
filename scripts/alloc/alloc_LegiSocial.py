# scripts/alloc/alloc_LegiSocial.py

import json
import re
import sys
import requests
from bs4 import BeautifulSoup

URL_LEGISOCIAL = "https://www.legisocial.fr/reperes-sociaux/taux-cotisations-sociales-urssaf-2025.html"

def parse_taux(text: str) -> float | None:
    """
    Nettoie un texte (ex: "3,45 %"), le convertit en float (3.45)
    puis en taux réel (0.0345).
    """
    if not text:
        return None
    try:
        cleaned_text = text.replace(',', '.').replace('%', '').strip()
        numeric_part = re.search(r"([0-9]+\.?[0-9]*)", cleaned_text)
        if not numeric_part:
            return None
        taux = float(numeric_part.group(1)) / 100.0
        return round(taux, 5)
    except (ValueError, AttributeError):
        return None

def make_payload(plein, reduit):
    return {
        "id": "allocations_familiales",
        "type": "cotisation",
        "libelle": "Allocations familiales",
        "base": "brut",
        "valeurs": {
            "salarial": None,
            "patronal_plein": plein,
            "patronal_reduit": reduit
        },
        "meta": {
            "source": [{"url": URL_LEGISOCIAL, "label": "LegiSocial", "date_doc": ""}],
            "generator": "scripts/alloc/alloc_LegiSocial.py"
        }
    }

def get_taux_alloc_legisocial() -> dict | None:
    """
    Scrape LegiSocial pour trouver les taux plein et réduit.
    STRATÉGIE IDENTIQUE :
      1) Trouver le titre contenant 'Quels sont les taux'
      2) Prendre la table qui suit
      3) Dans les lignes 'allocations familiales', lire la 5ᵉ cellule (index 4)
      4) Classer réduit si '≤' ou '<' dans le libellé ; plein si '>' dans le libellé
    """
    # print(f"Scraping de l'URL : {URL_LEGISOCIAL}...")
    response = requests.get(URL_LEGISOCIAL, timeout=20, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.0.0 Safari/537.36"
    })
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    
    # 1) Trouver la table principale des cotisations
    table_title = soup.find(lambda tag: tag.name in ['h2', 'h3'] and 'Quels sont les taux' in tag.get_text())
    if not table_title:
        raise ValueError("Titre de la table principale des cotisations introuvable.")
        
    table = table_title.find_next('table')
    if not table:
        raise ValueError("Table des cotisations introuvable après le titre.")

    # 2) Parcourir les lignes pour trouver les deux taux
    taux_trouves = {}
    tbody = table.find('tbody') or table
    for row in tbody.find_all('tr'):
        cells = row.find_all('td')
        if len(cells) > 4:
            libelle = cells[0].get_text().lower()
            if "allocations familiales" in libelle:
                taux_text = cells[4].get_text()
                taux = parse_taux(taux_text)
                
                if taux is not None:
                    # 3) Classification identique : signes dans le libellé
                    if "≤" in libelle or "<" in libelle:
                        # print(f"Taux Allocations Familiales (réduit) trouvé : {taux*100:.2f}%")
                        taux_trouves['reduit'] = taux
                    elif ">" in libelle:
                        # print(f"Taux Allocations Familiales (plein) trouvé : {taux*100:.2f}%")
                        taux_trouves['plein'] = taux
    
    if "reduit" in taux_trouves and "plein" in taux_trouves:
        return taux_trouves
    else:
        raise ValueError("Impossible de trouver les deux taux (réduit et plein) pour les allocations familiales.")

if __name__ == "__main__":
    try:
        tous_les_taux = get_taux_alloc_legisocial()
        payload = make_payload(tous_les_taux.get('plein'), tous_les_taux.get('reduit'))
        print(json.dumps(payload, ensure_ascii=False))
        # succès si les deux valeurs sont présentes
        sys.exit(0 if (payload["valeurs"]["patronal_plein"] is not None and payload["valeurs"]["patronal_reduit"] is not None) else 2)
    except Exception as e:
        print(json.dumps(make_payload(None, None), ensure_ascii=False))
        print(f"ERREUR : {e}", file=sys.stderr)
        sys.exit(2)
