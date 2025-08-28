# scripts/PSS_AI.py

import json
import os
import requests
from bs4 import BeautifulSoup
from openai import OpenAI
from googlesearch import search
from dotenv import load_dotenv
load_dotenv()

# --- Fichiers de configuration ---
FICHIER_ENTREPRISE = 'config/parametres_entreprise.json'
SEARCH_QUERY = "plafonds sécurité sociale URSSAF 2025"

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

def get_plafonds_ss_via_ai() -> dict | None:
    """
    Orchestre la recherche Google et l'extraction par IA des plafonds de la Sécurité Sociale.
    """
    # --- 1. Construction du prompt demandant un JSON structuré ---
    prompt_template = """
    Analyse le texte suivant et extrais le barème complet des Plafonds de la Sécurité Sociale pour 2025.
    Je veux toutes les périodicités : Année, Trimestre, Mois, Quinzaine, Semaine, Jour, Heure.

    Retourne le résultat dans un objet JSON valide et minifié.
    Les clés doivent être en français, en minuscule, comme dans l'exemple. Les valeurs doivent être des nombres entiers.

    Ne fournis AUCUNE explication, juste le JSON. Le format doit être EXACTEMENT comme suit :
    {"annuel":47100,"trimestriel":11775,"mensuel":3925,"quinzaine":1963,"hebdomadaire":906,"journalier":216,"horaire":29}

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

            # Validation pour s'assurer que le JSON est complet
            expected_keys = ["annuel", "trimestriel", "mensuel", "quinzaine", "hebdomadaire", "journalier", "horaire"]
            if data and all(key in data for key in expected_keys):
                print(f"✅ JSON valide et complet extrait de la page !")
                return data
            else:
                print("   - Le JSON extrait est incomplet ou invalide, passage à la page suivante.")
        except Exception as e:
            print(f"   - ERREUR inattendue : {e}. Passage à la page suivante.")

    print("\n❌ ERREUR FATALE : Aucune donnée valide n'a pu être extraite.")
    return None

def update_config_file(nouveaux_plafonds: dict):
    """
    Fonction identique à celle du script original.
    """
    try:
        with open(FICHIER_ENTREPRISE, 'r', encoding='utf-8') as f:
            config = json.load(f)
        
        constantes = config['PARAMETRES_ENTREPRISE']['constantes_paie_2025']
        
        if constantes.get('plafonds_securite_sociale') == nouveaux_plafonds:
            print(f"Les plafonds de la SS dans '{FICHIER_ENTREPRISE}' sont déjà à jour.")
            return

        print("Mise à jour de l'objet des plafonds de la Sécurité Sociale...")
        constantes['plafonds_securite_sociale'] = nouveaux_plafonds
        
        if 'plafond_ss_mensuel' in constantes:
            del constantes['plafond_ss_mensuel']
        
        with open(FICHIER_ENTREPRISE, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
            
        print(f"✅ Le fichier '{FICHIER_ENTREPRISE}' a été mis à jour avec succès.")
        
    except Exception as e:
        print(f"ERREUR : Une erreur est survenue lors de la mise à jour : {e}")

if __name__ == "__main__":
    valeurs_plafonds = get_plafonds_ss_via_ai()
    
    if valeurs_plafonds is not None:
        update_config_file(valeurs_plafonds)