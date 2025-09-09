# scripts/assurancechomage/assurancechomage_AI.py

import json
import os
from datetime import datetime
import sys

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from googlesearch import search
from openai import OpenAI

load_dotenv()

# Requête de recherche plus directe et précise
SEARCH_QUERY = "taux cotisation chômage employeur 2025"
GENERATOR = "scripts/assurancechomage/assurancechomage_AI.py"

def make_payload(rate, source_url=None):
    """Crée la charge utile JSON finale dans le format attendu par l'orchestrateur."""
    return {
        "id": "assurance_chomage",
        "type": "cotisation", # CORRIGÉ
        "libelle": "Assurance Chômage",
        "base": "brut", # CORRIGÉ
        "valeurs": {"salarial": None, "patronal": rate}, # CORRIGÉ
        "meta": {
            "source": ([{"url": source_url, "label": "Source via Recherche + IA", "date_doc": ""}] if source_url else []),
            "scraped_at": datetime.now().isoformat(),
            "generator": GENERATOR,
            "method": "ai"
        },
    }

def to_rate(v):
    """Convertit une valeur en taux (décimal)."""
    if v is None:
        return None
    try:
        return round(float(str(v).replace(",", ".")) / 100.0, 5)
    except (ValueError, TypeError):
        return None

def extract_with_gpt(page_text: str, current_year: str):
    """
    Demande à l'IA d'extraire le taux employeur avec un prompt simple et direct.
    """
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("ERREUR: La clé API OpenAI est manquante.", file=sys.stderr)
        return None

    try:
        client = OpenAI()
        # --- PROMPT SIMPLE ET ROBUSTE ---
        prompt = f"""
Tu es un expert de la paie en France. Pour l'année {current_year}, trouve le taux de la "Contribution d'assurance chômage" pour l'employeur.

Règles :
1.  Cherche le taux général ("taux de droit commun").
2.  Ignore les taux spéciaux (CDD, intermittents, etc.).
3.  Réponds UNIQUEMENT en JSON avec ce format : {{"patronal": 4.05}}

Si la valeur n'est pas claire, renvoie : {{"patronal": null}}

TEXTE :
---
{page_text[:12000]}
---
"""
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": "Assistant d'extraction de données, sortie JSON stricte."},
                {"role": "user", "content": prompt},
            ],
            temperature=0,
        )
        raw = resp.choices[0].message.content.strip()
        print(f"   - Réponse brute de l'IA : {raw}", file=sys.stderr)
        data = json.loads(raw)
        return data
    except Exception as e:
        print(f"   - ERREUR lors de l'appel à l'API OpenAI : {e}", file=sys.stderr)
        return None

def get_taux_chomage_via_ai():
    """Orchestre la recherche et l'extraction du taux."""
    current_year = str(datetime.now().year)
    print(f"Lancement de la recherche pour l'année {current_year}...", file=sys.stderr)
    try:
        results = list(search(SEARCH_QUERY, num_results=5, lang="fr"))
    except Exception as e:
        print(f"ERREUR lors de la recherche Google : {e}", file=sys.stderr)
        return None, None

    if not results:
        print("Aucun résultat de recherche trouvé.", file=sys.stderr)
        return None, None

    for i, url in enumerate(results, 1):
        print(f"\n--- Tentative {i}/{len(results)} sur l'URL : {url} ---", file=sys.stderr)
        try:
            r = requests.get(url, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
            r.raise_for_status()
            soup = BeautifulSoup(r.text, "html.parser")
            page_text = soup.get_text(" ", strip=True)

            data = extract_with_gpt(page_text, current_year)
            if not data:
                print("   - L'IA n'a retourné aucune donnée.", file=sys.stderr)
                continue

            patronal_pct = data.get("patronal")
            rate = to_rate(patronal_pct)
            
            if rate is not None:
                print(f"✅ Taux valide trouvé : {rate*100:.2f}%", file=sys.stderr)
                return rate, url
            else:
                print(f"   - L'IA n'a pas trouvé de taux valide sur cette page.", file=sys.stderr)

        except Exception as e:
            print(f"   - ERREUR lors du traitement de la page : {e}", file=sys.stderr)
            continue

    print("\n❌ Le taux n'a pu être déterminé sur aucune des pages analysées.", file=sys.stderr)
    return None, None

if __name__ == "__main__":
    rate, src = get_taux_chomage_via_ai()
    final_payload = make_payload(rate, src)
    print(json.dumps(final_payload, ensure_ascii=False))