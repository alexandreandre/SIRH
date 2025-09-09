# scripts/dialoguesocial/dialoguesocial_AI.py

import json
import os
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

SEARCH_QUERY = "taux contribution dialogue social 2025 urssaf"

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

def _extract_rate_with_gpt(page_text: str) -> dict | None:
    """Demande au modèle d'extraire le taux."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("ERREUR: La clé API OpenAI est manquante.", file=sys.stderr)
        return None
    
    client = OpenAI(api_key=api_key)
    current_year = datetime.now().year

    prompt = (
        f"Pour l'année {current_year}, trouve le taux de la 'Contribution au financement du dialogue social'. C'est un petit pourcentage patronal.\n\n"
        "Contraintes:\n"
        "- Réponds UNIQUEMENT en JSON avec la clé: {\"taux\": <nombre|null>}\n"
        "- La valeur doit être le pourcentage (ex: 0.016).\n"
        "- Si la valeur est manquante, mets `null`.\n\n"
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

def build_payload(rate_pct: float | None, source_url: str | None) -> dict:
    """Construit la charge utile JSON finale pour l'orchestrateur."""
    rate_decimal = None
    if rate_pct is not None:
        try:
            rate_decimal = round(float(str(rate_pct).replace(",", ".")) / 100.0, 6)
        except (ValueError, TypeError):
            rate_decimal = None

    return {
        "id": "dialogue_social",
        "type": "cotisation",
        "libelle": "Contribution au dialogue social",
        "sections": {
            "salarial": None,
            "patronal": rate_decimal
        },
        "meta": {
            "source": ([{"url": source_url, "label": "Web + IA", "date_doc": ""}] if source_url else []),
            "scraped_at": iso_now(),
            "generator": "scripts/dialoguesocial/dialoguesocial_AI.py",
            "method": "ai",
        },
    }

def main() -> None:
    """Orchestre la recherche et l'extraction du taux via l'IA."""
    print(f"Lancement de la recherche Google : '{SEARCH_QUERY}'...", file=sys.stderr)
    try:
        results = list(search(SEARCH_QUERY, num_results=5, lang="fr"))
    except Exception as e:
        print(f"ERREUR lors de la recherche Google : {e}", file=sys.stderr)
        results = []

    if not results:
        sys.exit(1)

    final_rate = None
    source_url = None

    for url in results:
        print(f"\n--- Tentative sur l'URL : {url} ---", file=sys.stderr)
        txt = _fetch_text_with_selenium(url)
        if not txt:
            continue
            
        data = _extract_rate_with_gpt(txt)
        if data and data.get("taux") is not None:
            print("✅ Taux valide extrait avec succès.", file=sys.stderr)
            final_rate = data.get("taux")
            source_url = url
            break
        else:
            print("   - Donnée non trouvée, passage à l'URL suivante.", file=sys.stderr)

    # On génère le payload même si le taux est None pour que l'orchestrateur puisse le comparer
    payload = build_payload(final_rate, source_url)
    if final_rate is None:
        print("\nERREUR CRITIQUE : Impossible d'extraire le taux.", file=sys.stderr)
        print(json.dumps(payload, ensure_ascii=False))
        sys.exit(1)

    print(json.dumps(payload, ensure_ascii=False))

if __name__ == "__main__":
    main()