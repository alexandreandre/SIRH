# scripts/MMIDsalarial/MMIDsalarial_AI.py

import json
import os
import sys
from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup
from openai import OpenAI
from googlesearch import search
from dotenv import load_dotenv
load_dotenv()

SEARCH_QUERY = "taux cotisation salariale maladie supplémentaire Alsace-Moselle URSSAF 2025"

# --- FONCTIONS UTILITAIRES ---

def iso_now() -> str:
    """Retourne la date et l'heure actuelles au format ISO 8601 UTC."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def extract_value_with_gpt(page_text: str, prompt: str) -> str | None:
    """
    Interroge GPT-4o-mini pour extraire une valeur.
    """
    if not os.getenv("OPENAI_API_KEY"):
        print("ERREUR : La variable d'environnement OPENAI_API_KEY n'est pas définie.", file=sys.stderr)
        return None
    try:
        client = OpenAI()
        print("   - Envoi de la requête à l'API GPT-4o-mini pour extraction...", file=sys.stderr)
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "Tu es un expert en extraction de données."},
                {"role": "user", "content": prompt}
            ],
            temperature=0,
            max_tokens=10
        )
        extracted_text = response.choices[0].message.content.strip()
        print(f"   - Réponse brute de l'API : '{extracted_text}'", file=sys.stderr)
        return extracted_text
    except Exception as e:
        print(f"   - ERREUR : L'appel à l'API OpenAI a échoué. Raison : {e}", file=sys.stderr)
        return None

# --- FONCTION DE SCRAPING VIA IA ---

def get_taux_alsace_moselle_via_ai() -> float | None:
    """
    Orchestre la recherche Google et l'extraction par IA pour trouver le taux.
    """
    prompt_template = """
    Analyse le texte suivant et trouve le taux de la "Cotisation salariale maladie supplémentaire" applicable en Alsace-Moselle.
    Attention, on parle bien du taux salarial, et pas patronal.
    Réponds UNIQUEMENT avec le taux en pourcentage sous forme de nombre à virgule, en utilisant un point comme séparateur décimal.
    Exemple de réponse attendue : 1.30
    Si tu ne trouves pas la valeur, réponds "None".
    Voici le texte :
    ---
    """

    print(f"Lancement de la recherche Google : '{SEARCH_QUERY}'...", file=sys.stderr)
    try:
        search_results = list(search(SEARCH_QUERY, num_results=3, lang="fr"))
    except Exception as e:
        print(f"ERREUR : La recherche Google a échoué : {e}", file=sys.stderr)
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
            extracted_text = extract_value_with_gpt(page_text, final_prompt)

            if extracted_text and extracted_text.lower() != 'none':
                taux_percent = float(extracted_text.replace(',', '.'))
                taux_final = round(taux_percent / 100.0, 5)
                print(f"✅ Valeur trouvée et validée ! Taux : {taux_final*100:.2f}%", file=sys.stderr)
                return taux_final
            else:
                print("   - Aucune valeur extraite de cette page, passage à la suivante.", file=sys.stderr)
        except Exception as e:
            print(f"   - ERREUR inattendue : {e}. Passage à la page suivante.", file=sys.stderr)

    print("\n❌ ERREUR FATALE : Aucune valeur n'a pu être extraite après avoir essayé toutes les pages.", file=sys.stderr)
    return None

# --- FONCTION PRINCIPALE ---

def main():
    """
    Orchestre le scraping IA et génère la sortie JSON pour l'orchestrateur.
    """
    taux = get_taux_alsace_moselle_via_ai()

    if taux is None:
        print("ERREUR CRITIQUE: Le taux n'a pas pu être récupéré via l'IA.", file=sys.stderr)
        sys.exit(1)

    # Assemblage du payload final, identique en structure aux autres scripts
    payload = {
        "id": "maladie_alsace_moselle",
        "type": "taux_cotisation_specifique",
        "libelle": "Taux de cotisation salariale maladie - Alsace-Moselle",
        "sections": {
            "alsace_moselle": {
                "taux_salarial": taux
            }
        },
        "meta": {
            "source": [{
                "url": f"google_search:?q={SEARCH_QUERY.replace(' ', '+')}",
                "label": "Recherche Google + Extraction AI",
                "date_doc": ""
            }],
            "scraped_at": iso_now(),
            "generator": "scripts/MMIDsalarial/MMIDsalarial_AI.py",
            "method": "ai"
        }
    }

    # Impression du JSON final sur la sortie standard
    print(json.dumps(payload, ensure_ascii=False))


if __name__ == "__main__":
    main()