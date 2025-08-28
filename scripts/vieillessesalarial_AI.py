# scripts/vieillessesalarial_AI.py

import json
import os
import requests
from bs4 import BeautifulSoup
from openai import OpenAI
from googlesearch import search

# --- Fichiers de configuration ---
FICHIER_TAUX = 'config/taux_cotisations.json'
SEARCH_QUERY = "taux cotisation assurance vieillesse salariale urssaf 2025"

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
    except Exception as e:
        print(f"   - ERREUR : L'appel à l'API ou le parsing JSON a échoué. Raison : {e}")
        return None

def get_taux_vieillesse_salarial_via_ai() -> dict | None:
    """
    Orchestre la recherche Google et l'extraction par IA des taux de vieillesse salariaux.
    """
    # --- 1. Construction du prompt demandant un JSON avec deux clés ---
    prompt_template = """
    Analyse le texte suivant de la section "Taux de cotisations salarié" et extrais les deux taux de la cotisation salariale "Assurance vieillesse" pour 2025 :
    1. Le taux sur la totalité de la rémunération (déplafonné).
    2. Le taux dans la limite du plafond (plafonné).

    Retourne le résultat dans un objet JSON valide et minifié.
    Les clés doivent être "deplafond" et "plafond". Les valeurs doivent être les taux en pourcentage.

    Ne fournis AUCUNE explication, juste le JSON. Le format doit être EXACTEMENT comme suit :
    {"deplafond":0.40,"plafond":6.90}

    Voici le texte à analyser :
    ---
    """

    # --- 2. Boucle sur les résultats de recherche ---
    print(f"Lancement de la recherche Google : '{SEARCH_QUERY}'...")
    search_results = list(search(SEARCH_QUERY, num_results=3, lang="fr"))
    if not search_results:
        print("ERREUR : La recherche Google n'a retourné aucun résultat.")
        return None

    for i, page_url in enumerate(search_results):
        print(f"\n--- Tentative {i+1}/3 sur la page : {page_url} ---")
        try:
            response = requests.get(page_url, timeout=20, headers={'User-Agent': 'Mozilla/5.0'})
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")
            page_text = soup.get_text(" ", strip=True)

            final_prompt = prompt_template + page_text[:12000]
            data = extract_json_with_gpt(page_text, final_prompt)

            if data and all(key in data for key in ["deplafond", "plafond"]):
                print(f"✅ JSON valide et complet extrait de la page !")
                # On convertit les pourcentages en taux utilisables
                taux_deplafond = round(data["deplafond"] / 100.0, 5)
                taux_plafond = round(data["plafond"] / 100.0, 5)
                return {"deplafond": taux_deplafond, "plafond": taux_plafond}
            else:
                print("   - Le JSON extrait est incomplet ou invalide, passage à la page suivante.")
        except Exception as e:
            print(f"   - ERREUR inattendue : {e}. Passage à la page suivante.")

    print("\n❌ ERREUR FATALE : Aucune donnée valide n'a pu être extraite.")
    return None

def update_config_file(nouveaux_taux: dict):
    """
    Fonction adaptée de celle du script original.
    """
    try:
        with open(FICHIER_TAUX, 'r', encoding='utf-8') as f:
            config = json.load(f)
        
        cotisation_deplafond = config['TAUX_COTISATIONS']['retraite_secu_deplafond']
        cotisation_plafond = config['TAUX_COTISATIONS']['retraite_secu_plafond']

        print(f"\nMise à jour de 'retraite_secu_deplafond' (salarial) : {cotisation_deplafond['salarial']} -> {nouveaux_taux['deplafond']}")
        print(f"Mise à jour de 'retraite_secu_plafond' (salarial)   : {cotisation_plafond['salarial']} -> {nouveaux_taux['plafond']}")

        cotisation_deplafond['salarial'] = nouveaux_taux['deplafond']
        cotisation_plafond['salarial'] = nouveaux_taux['plafond']
        
        with open(FICHIER_TAUX, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
            
        print(f"✅ Le fichier '{FICHIER_TAUX}' a été mis à jour avec succès.")
        
    except Exception as e:
        print(f"ERREUR : Une erreur est survenue lors de la mise à jour : {e}")

if __name__ == "__main__":
    taux = get_taux_vieillesse_salarial_via_ai()
    
    if taux is not None:
        update_config_file(taux)