# scripts/SMIC/SMIC_AI.py

import json
import os
import sys
from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from googlesearch import search
from openai import OpenAI

load_dotenv()

# --- Constantes ---
SEARCH_QUERY = "montant smic horaire brut URSSAF 2025"

# --- UTILITAIRES ---
def iso_now() -> str:
    """Retourne la date et l'heure actuelles au format ISO 8601 UTC."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def extract_json_with_gpt(page_text: str, prompt: str) -> dict | None:
    """
    Interroge GPT-4o-mini et s'attend à recevoir une chaîne de caractères JSON valide.
    """
    if not os.getenv("OPENAI_API_KEY"):
        print("ERREUR : La variable d'environnement OPENAI_API_KEY n'est pas définie.", file=sys.stderr)
        return None
    try:
        client = OpenAI()
        print("   - Envoi de la requête à l'API GPT-4o-mini pour extraction JSON...", file=sys.stderr)
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": "Tu es un expert en extraction de données qui répond au format JSON."},
                {"role": "user", "content": prompt}
            ],
            temperature=0
        )
        extracted_text = response.choices[0].message.content.strip()
        print(f"   - Réponse brute de l'API : {extracted_text}", file=sys.stderr)
        return json.loads(extracted_text)
    except Exception as e:
        print(f"   - ERREUR : L'appel à l'API ou le parsing JSON a échoué. Raison : {e}", file=sys.stderr)
        return None

# --- SCRAPER IA ---
def get_smic_via_ai() -> dict | None:
    """
    Orchestre la recherche Google et l'extraction par IA des différents montants du SMIC.
    """
    prompt_template = """
    Analyse le texte suivant et extrais les montants du SMIC horaire brut pour 2025 pour les 3 cas suivants :
    1. Le cas général.
    2. Pour les salariés entre 17 et 18 ans (ou 17 ans révolus).
    3. Pour les salariés de moins de 17 ans.

    Retourne le résultat dans un objet JSON valide et minifié.
    Les clés doivent être "cas_general", "entre_17_et_18_ans", "moins_de_17_ans".
    Les valeurs doivent être des nombres.

    Le format doit être EXACTEMENT comme suit :
    {"cas_general":11.88,"entre_17_et_18_ans":10.69,"moins_de_17_ans":9.50}

    Voici le texte à analyser :
    ---
    """

    print(f"Lancement de la recherche Google : '{SEARCH_QUERY}'...", file=sys.stderr)
    try:
        search_results = list(search(SEARCH_QUERY, num_results=3, lang="fr"))
    except Exception as e:
        print(f"ERREUR lors de la recherche Google : {e}", file=sys.stderr)
        return None

    if not search_results:
        print("ERREUR : La recherche Google n'a retourné aucun résultat.", file=sys.stderr)
        return None

    for i, page_url in enumerate(search_results):
        print(f"\n--- Tentative {i+1}/{len(search_results)} sur la page : {page_url} ---", file=sys.stderr)
        try:
            response = requests.get(page_url, timeout=20, headers={'User-Agent': 'Mozilla/5.0'})
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")
            page_text = soup.get_text(" ", strip=True)

            final_prompt = prompt_template + page_text[:12000]
            data = extract_json_with_gpt(page_text, final_prompt)

            expected_keys = ["cas_general", "entre_17_et_18_ans", "moins_de_17_ans"]
            if data and all(key in data for key in expected_keys):
                print(f"✅ JSON valide et complet extrait de la page !", file=sys.stderr)
                return data
            else:
                print("   - Le JSON extrait est incomplet ou invalide, passage à la page suivante.", file=sys.stderr)
        except Exception as e:
            print(f"   - ERREUR inattendue : {e}. Passage à la page suivante.", file=sys.stderr)

    print("\n❌ ERREUR FATALE : Aucune donnée valide n'a pu être extraite.", file=sys.stderr)
    return None

# --- FONCTION PRINCIPALE ---
def main():
    """Orchestre le scraping IA et génère la sortie JSON pour l'orchestrateur."""
    raw_smic_data = get_smic_via_ai()
    
    if not raw_smic_data:
        print("ERREUR CRITIQUE: Le scraping du SMIC via IA a échoué.", file=sys.stderr)
        sys.exit(1)

    # Normalisation des clés pour correspondre au scraper principal
    smic_data = {
        "cas_general": raw_smic_data.get("cas_general"),
        "jeune_17_ans": raw_smic_data.get("entre_17_et_18_ans"),
        "jeune_moins_17_ans": raw_smic_data.get("moins_de_17_ans")
    }

    payload = {
        "id": "smic_horaire",
        "type": "bareme_horaire",
        "libelle": "Salaire Minimum Interprofessionnel de Croissance (SMIC) - Taux horaire",
        "sections": smic_data,
        "meta": {
            "source": [{
                "url": f"google_search:?q={SEARCH_QUERY.replace(' ', '+')}",
                "label": "Recherche Google + Extraction AI",
                "date_doc": ""
            }],
            "scraped_at": iso_now(),
            "generator": "scripts/SMIC/SMIC_AI.py",
            "method": "ai"
        }
    }
    
    print(json.dumps(payload, ensure_ascii=False))

if __name__ == "__main__":
    main()