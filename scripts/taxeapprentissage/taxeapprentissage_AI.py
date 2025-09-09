# scripts/taxeapprentissage/taxeapprentissage_AI.py

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

SEARCH_QUERY = "taux taxe d'apprentissage 2025 part principale et solde"

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
    """Demande au modèle d'extraire la décomposition des taux."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("ERREUR: La clé API OpenAI est manquante.", file=sys.stderr)
        return None
    
    client = OpenAI(api_key=api_key)
    current_year = datetime.now().year

    prompt = (
        f"Pour l'année {current_year}, extrais les taux de la taxe d'apprentissage en France.\n"
        "Je veux la décomposition complète :\n"
        "1. La 'part principale' pour la métropole ET pour l'Alsace-Moselle.\n"
        "2. Le 'solde' pour la métropole ET pour l'Alsace-Moselle (si le solde n'est pas dû, le taux est 0).\n\n"
        "Réponds UNIQUEMENT en JSON avec la structure suivante (valeurs en pourcentage, ex: 0.59) :\n"
        """
        {
          "part_principale": {
            "taux_metropole": 0.59,
            "taux_alsace_moselle": 0.44
          },
          "solde": {
            "taux_metropole": 0.09,
            "taux_alsace_moselle": 0.0
          }
        }
        """
        "\nTexte à analyser:\n---\n"
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

    # Convertit les pourcentages en taux décimaux
    rates["part_principale"]["taux_metropole"] = _to_rate(rates["part_principale"]["taux_metropole"])
    rates["part_principale"]["taux_alsace_moselle"] = _to_rate(rates["part_principale"]["taux_alsace_moselle"])
    rates["solde"]["taux_metropole"] = _to_rate(rates["solde"]["taux_metropole"])
    rates["solde"]["taux_alsace_moselle"] = _to_rate(rates["solde"]["taux_alsace_moselle"])
    
    # Calcule le total
    rates["total"] = {
        "taux_metropole": rates["part_principale"]["taux_metropole"] + rates["solde"]["taux_metropole"],
        "taux_alsace_moselle": rates["part_principale"]["taux_alsace_moselle"] + rates["solde"]["taux_alsace_moselle"]
    }

    return {
        "id": "taxe_apprentissage",
        "type": "cotisation",
        "libelle": "Taxe d'Apprentissage",
        "sections": {
            "salarial": None,
            "part_principale": rates.get("part_principale"),
            "solde": rates.get("solde"),
            "total": rates.get("total")
        },
        "meta": {
            "source": ([{"url": source_url, "label": "Web + IA", "date_doc": ""}] if source_url else []),
            "scraped_at": iso_now(),
            "generator": "scripts/taxeapprentissage/taxeapprentissage_AI.py",
            "method": "ai",
        },
    }

def main() -> None:
    """Orchestre la recherche et l'extraction des taux via l'IA."""
    print(f"Lancement de la recherche Google : '{SEARCH_QUERY}'...", file=sys.stderr)
    try:
        results = list(search(SEARCH_QUERY, num_results=5, lang="fr"))
    except Exception as e:
        print(f"ERREUR lors de la recherche Google : {e}", file=sys.stderr)
        results = []

    if not results:
        sys.exit(1)

    final_rates = None
    source_url = None

    for url in results:
        print(f"\n--- Tentative sur l'URL : {url} ---", file=sys.stderr)
        txt = _fetch_text_with_selenium(url)
        if not txt:
            continue
            
        rates = _extract_rates_with_gpt(txt)
        # On vérifie la structure complète
        if (rates and "part_principale" in rates and "solde" in rates and
            "taux_metropole" in rates["part_principale"] and "taux_alsace_moselle" in rates["part_principale"] and
            "taux_metropole" in rates["solde"] and "taux_alsace_moselle" in rates["solde"]):
            print("✅ Structure complète extraite avec succès.", file=sys.stderr)
            final_rates = rates
            source_url = url
            break
        else:
            print("   - Données incomplètes extraites, passage à l'URL suivante.", file=sys.stderr)

    if not final_rates:
        print("\nERREUR CRITIQUE : Impossible d'extraire la structure complète des taux.", file=sys.stderr)
        payload = build_payload({"part_principale": {}, "solde": {}}, None)
        print(json.dumps(payload, ensure_ascii=False))
        sys.exit(1)

    payload = build_payload(final_rates, source_url)
    print(json.dumps(payload, ensure_ascii=False))

if __name__ == "__main__":
    main()