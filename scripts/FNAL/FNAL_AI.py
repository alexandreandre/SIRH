# scripts/FNAL/FNAL_AI.py
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

SEARCH_QUERY = "taux cotisation FNAL URSSAF 2025 moins de 50 salariés 50 salariés et plus"

def iso_now() -> str:
    """Retourne la date et l'heure actuelles au format ISO 8601 UTC."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def _fetch_text_with_selenium(url: str) -> str | None:
    """Récupère le texte brut d'une page web en utilisant Selenium pour plus de fiabilité."""
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
        time.sleep(2) # Attendre un peu si la page utilise du JavaScript

        soup = BeautifulSoup(driver.page_source, "html.parser")
        return soup.get_text(" ", strip=True)
    except Exception as e:
        print(f"   - ERREUR de fetch (Selenium) sur {url}: {e}", file=sys.stderr)
        return None
    finally:
        if driver:
            driver.quit()

def _extract_rates_with_gpt(page_text: str) -> dict[str, float | None]:
    """Demande au modèle d'extraire les deux taux FNAL."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("ERREUR: La clé API OpenAI est manquante.", file=sys.stderr)
        return {"patronal_moins_50": None, "patronal_50_et_plus": None}
    
    client = OpenAI(api_key=api_key)
    current_year = datetime.now().year

    prompt = (
        f"Extrait les deux pourcentages de la cotisation patronale « FNAL » en France pour l'année {current_year}:\n"
        "- Le taux pour les entreprises de MOINS de 50 salariés.\n"
        "- Le taux pour les entreprises de 50 salariés ET PLUS.\n\n"
        "Contraintes:\n"
        "- Réponds UNIQUEMENT en JSON avec les clés: {\"taux_moins_50\": <nombre|null>, \"taux_50_et_plus\": <nombre|null>}\n"
        "- Utilise un point pour les décimales, sans signe %.\n"
        "- Si une valeur est manquante, mets `null`.\n\n"
        "Texte:\n---\n"
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
        data = json.loads(raw)
        
        def _to_rate(key: str) -> float | None:
            val = data.get(key)
            if val is None: return None
            return round(float(str(val).replace(",", ".")) / 100.0, 6)

        return {
            "patronal_moins_50": _to_rate("taux_moins_50"),
            "patronal_50_et_plus": _to_rate("taux_50_et_plus")
        }
    except Exception as e:
        print(f"   - ERREUR d'extraction IA: {e}", file=sys.stderr)
        return {"patronal_moins_50": None, "patronal_50_et_plus": None}

def build_payload(rates: dict, source_url: str | None) -> dict:
    """Construit la charge utile JSON finale pour l'orchestrateur."""
    return {
        "id": "fnal",
        "type": "cotisation",
        "libelle": "Fonds National d’Aide au Logement (FNAL)",
        "sections": {
            "salarial": None,
            "patronal_moins_50": rates.get("patronal_moins_50"),
            "patronal_50_et_plus": rates.get("patronal_50_et_plus")
        },
        "meta": {
            "source": ([{"url": source_url, "label": "Web + IA", "date_doc": ""}] if source_url else []),
            "scraped_at": iso_now(),
            "generator": "scripts/FNAL/FNAL_AI.py",
            "method": "ai",
        },
    }

def main() -> None:
    """Orchestre la recherche et l'extraction des deux taux FNAL via l'IA."""
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
        if rates.get("patronal_moins_50") is not None and rates.get("patronal_50_et_plus") is not None:
            print("✅ Les deux taux FNAL ont été extraits avec succès.", file=sys.stderr)
            final_rates = rates
            source_url = url
            break
        else:
            print("   - Données incomplètes extraites, passage à l'URL suivante.", file=sys.stderr)

    if not final_rates:
        print("\nERREUR CRITIQUE : Impossible d'extraire les deux taux FNAL après analyse des sources.", file=sys.stderr)
        payload = build_payload({}, None)
        print(json.dumps(payload, ensure_ascii=False))
        sys.exit(1)

    payload = build_payload(final_rates, source_url)
    print(json.dumps(payload, ensure_ascii=False))

if __name__ == "__main__":
    main()