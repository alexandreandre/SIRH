# scripts/CFP/CFP_AI.py

import json
import os
import re
import sys
import time
from datetime import datetime, timezone

from bs4 import BeautifulSoup
from dotenv import load_dotenv
from googlesearch import search
from openai import OpenAI
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service as ChromeService
from webdriver_manager.chrome import ChromeDriverManager

load_dotenv()

SEARCH_QUERY = "taux contribution formation professionnelle 2025 moins de 11 salariés 11 et plus"

# --- UTILITAIRES ---
def iso_now() -> str:
    """Retourne la date et l'heure actuelles au format ISO 8601 UTC."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def _fetch_text_with_selenium(url: str) -> str | None:
    """Récupère le texte brut d'une page web en utilisant Selenium."""
    driver = None
    try:
        chrome_options = Options()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.0.0 Safari/537.36")
        
        driver = webdriver.Chrome(service=ChromeService(ChromeDriverManager().install()), options=chrome_options)
        driver.set_page_load_timeout(30)
        driver.get(url)
        time.sleep(2)

        soup = BeautifulSoup(driver.page_source, "html.parser")
        return soup.get_text(" ", strip=True)
    except Exception as e:
        print(f"   - ERREUR de fetch (Selenium) sur {url}: {e}", file=sys.stderr)
        return None
    finally:
        if driver:
            driver.quit()

def _extract_rates_with_gpt(page_text: str) -> dict | None:
    """Demande au modèle d'extraire les deux taux CFP."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("ERREUR: La clé API OpenAI est manquante.", file=sys.stderr)
        return None
    
    client = OpenAI(api_key=api_key)
    current_year = datetime.now().year

    prompt = (
        f"Pour l'année {current_year}, extrais les deux taux de la 'Contribution à la Formation Professionnelle' (CFP) en France.\n"
        "- Le taux pour les entreprises de MOINS de 11 salariés.\n"
        "- Le taux pour les entreprises de 11 salariés ET PLUS.\n\n"
        "Contraintes:\n"
        "- Réponds UNIQUEMENT en JSON avec les clés: {{\"taux_moins_11\": <nombre|null>, \"taux_11_et_plus\": <nombre|null>}}\n"
        "- Les valeurs doivent être les pourcentages (ex: 0.55 ou 1.0).\n"
        "- Si une valeur est manquante, mets `null`.\n\n"
        "Texte à analyser:\n---\n"
        + page_text[:15000]
    )
    
    try:
        print("   - Appel à l'API GPT-4o-mini...", file=sys.stderr)
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            response_format={"type": "json_object"},
            temperature=0,
            messages=[
                {"role": "system", "content": "Assistant d'extraction. Ne renvoie que du JSON valide."},
                {"role": "user", "content": prompt},
            ],
        )
        raw = resp.choices[0].message.content.strip()
        print(f"   - Réponse brute de l'IA: {raw}", file=sys.stderr)
        return json.loads(raw)

    except Exception as e:
        print(f"   - ERREUR d'extraction IA: {e}", file=sys.stderr)
        return None

def build_payload(rates: dict, source_url: str | None) -> dict:
    """Construit la charge utile JSON finale pour l'orchestrateur."""
    def _to_rate(val):
        if val is None: return None
        return round(float(str(val).replace(",", ".")) / 100.0, 6)

    sections_data = {
        "salarial": None,
        "patronal_moins_11": _to_rate(rates.get("taux_moins_11")),
        "patronal_11_et_plus": _to_rate(rates.get("taux_11_et_plus"))
    }
    
    return {
        "id": "cfp",
        "type": "cotisation",
        "libelle": "Contribution à la Formation Professionnelle (CFP)",
        "sections": sections_data,
        "meta": {
            "source": ([{"url": source_url, "label": "Web + IA", "date_doc": ""}] if source_url else []),
            "scraped_at": iso_now(),
            "generator": "scripts/CFP/CFP_AI.py",
            "method": "ai",
        },
    }

def main() -> None:
    """Orchestre la recherche et l'extraction des deux taux CFP via l'IA."""
    print(f"Lancement de la recherche Google : '{SEARCH_QUERY}'...", file=sys.stderr)
    try:
        results = list(search(SEARCH_QUERY, num_results=5, lang="fr"))
    except Exception as e:
        print(f"ERREUR lors de la recherche Google : {e}", file=sys.stderr)
        results = []

    if not results:
        print("ERREUR : Aucun résultat de recherche.", file=sys.stderr)
        sys.exit(1)

    final_rates = None
    source_url = None

    for url in results:
        print(f"\n--- Tentative sur l'URL : {url} ---", file=sys.stderr)
        txt = _fetch_text_with_selenium(url)
        if not txt:
            continue
            
        rates = _extract_rates_with_gpt(txt)
        if rates and rates.get("taux_moins_11") is not None and rates.get("taux_11_et_plus") is not None:
            print("✅ Les deux taux CFP ont été extraits avec succès.", file=sys.stderr)
            final_rates = rates
            source_url = url
            break
        else:
            print("   - Données incomplètes extraites, passage à l'URL suivante.", file=sys.stderr)

    if not final_rates:
        print("\nERREUR CRITIQUE : Impossible d'extraire les deux taux CFP.", file=sys.stderr)
        payload = build_payload({}, None)
        print(json.dumps(payload, ensure_ascii=False))
        sys.exit(1)

    payload = build_payload(final_rates, source_url)
    print(json.dumps(payload, ensure_ascii=False))

if __name__ == "__main__":
    main()