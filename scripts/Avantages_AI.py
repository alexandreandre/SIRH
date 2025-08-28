# scripts/Avantages_AI.py (version avec prompt amélioré pour un JSON complet)

import json
import os
import requests
from bs4 import BeautifulSoup
from openai import OpenAI
from googlesearch import search

# --- Fichiers de configuration ---
FICHIER_ENTREPRISE = 'config/parametres_entreprise.json'
SEARCH_QUERY = "barème avantages en nature URSSAF 2025"

def extract_json_with_gpt(page_text: str, prompt: str) -> dict | None:
    """
    Interroge GPT-4o-mini et s'attend à recevoir une chaîne de caractères JSON valide.
    """
    if not os.getenv("OPENAI_API_KEY"):
        print("ERREUR : La variable d'environnement OPENAI_API_KEY n'est pas définie.")
        return None
    try:
        client = OpenAI()
        print("   - Envoi de la requête à l'API GPT-4o-mini pour extraction JSON...")
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
        print(f"   - Réponse brute de l'API : {extracted_text}")
        return json.loads(extracted_text)
    except json.JSONDecodeError:
        print("   - ERREUR : L'IA n'a pas retourné un JSON valide.")
        return None
    except Exception as e:
        print(f"   - ERREUR : L'appel à l'API OpenAI a échoué. Raison : {e}")
        return None

def get_avantages_via_ai() -> dict | None:
    """
    Orchestre la recherche Google et l'extraction JSON par IA, en cherchant sur 50 pages.
    """
    # --- NOUVEAU PROMPT AMÉLIORÉ ---
    # On donne un exemple complet avec toutes les tranches pour guider l'IA.
    prompt_template = """
    Analyse le texte suivant et extrais les 3 informations sur les avantages en nature pour 2025.
    Retourne le résultat dans un objet JSON valide et minifié.

    1.  **repas**: La valeur forfaitaire pour "1 repas".
    2.  **titre_restaurant**: L'exonération maximale de la part patronale pour un "titre-restaurant".
    3.  **logement**: Le "barème du logement" COMPLET. Il doit contenir TOUTES les tranches de rémunération présentes dans le tableau. Pour la dernière tranche, utilise une valeur numérique très élevée (ex: 999999.99) pour la clé "remuneration_max".

    Ne fournis AUCUNE explication, juste le JSON. Le format doit être EXACTEMENT comme suit :
    {"repas":5.45,"titre_restaurant":7.26,"logement":[{"remuneration_max":1962.50,"valeur_1_piece":78.70,"valeur_par_piece":42.10},{"remuneration_max":2354.99,"valeur_1_piece":91.80,"valeur_par_piece":58.90},{"remuneration_max":2747.49,"valeur_1_piece":104.80,"valeur_par_piece":78.70},{"remuneration_max":3532.49,"valeur_1_piece":117.90,"valeur_par_piece":98.20},{"remuneration_max":4317.49,"valeur_1_piece":144.50,"valeur_par_piece":124.50},{"remuneration_max":5102.49,"valeur_1_piece":170.40,"valeur_par_piece":150.40},{"remuneration_max":5887.49,"valeur_1_piece":196.80,"valeur_par_piece":183.30},{"remuneration_max":999999.99,"valeur_1_piece":222.70,"valeur_par_piece":209.60}]}

    Voici le texte à analyser :
    ---
    """

    # --- Boucle sur 50 résultats de recherche ---
    print(f"Lancement de la recherche Google : '{SEARCH_QUERY}'...")
    search_results = list(search(SEARCH_QUERY, num_results=50, lang="fr"))
    if not search_results:
        print("ERREUR : La recherche Google n'a retourné aucun résultat.")
        return None

    for i, page_url in enumerate(search_results):
        print(f"\n--- Tentative {i+1}/50 sur la page : {page_url} ---")
        try:
            response = requests.get(page_url, timeout=20, headers={'User-Agent': 'Mozilla/5.0'})
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")
            page_text = soup.get_text(" ", strip=True)

            final_prompt = prompt_template + page_text[:15000]
            data = extract_json_with_gpt(page_text, final_prompt)

            if data and all(key in data for key in ["repas", "titre_restaurant", "logement"]) and isinstance(data["logement"], list) and len(data["logement"]) > 1:
                print(f"✅ JSON valide et complet extrait de la page !")
                return data
            else:
                print("   - Le JSON extrait est incomplet ou invalide, passage à la page suivante.")

        except Exception as e:
            print(f"   - ERREUR inattendue : {e}. Passage à la page suivante.")

    print("\n❌ ERREUR FATALE : Aucune donnée valide n'a pu être extraite.")
    return None

def update_config_file(nouvelles_valeurs: dict):
    """
    Cette fonction reste identique.
    """
    try:
        with open(FICHIER_ENTREPRISE, 'r', encoding='utf-8') as f:
            config = json.load(f)
        if 'avantages_en_nature' not in config['PARAMETRES_ENTREPRISE']:
            config['PARAMETRES_ENTREPRISE']['avantages_en_nature'] = {}
        avantages = config['PARAMETRES_ENTREPRISE']['avantages_en_nature']
        print("\nMise à jour du fichier de configuration...")
        avantages['repas_valeur_forfaitaire'] = nouvelles_valeurs['repas']
        avantages['titre_restaurant_exoneration_max_patronale'] = nouvelles_valeurs['titre_restaurant']
        avantages['logement_bareme_forfaitaire'] = nouvelles_valeurs['logement']
        with open(FICHIER_ENTREPRISE, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        print(f"✅ Le fichier '{FICHIER_ENTREPRISE}' a été mis à jour avec succès.")
    except Exception as e:
        print(f"ERREUR : Une erreur est survenue lors de la mise à jour : {e}")

if __name__ == "__main__":
    valeurs = get_avantages_via_ai()
    
    if valeurs is not None:
        update_config_file(valeurs)