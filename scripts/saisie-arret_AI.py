# scripts/saisie-arret_AI.py

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
SEARCH_QUERY = "barème saisie sur salaire 2025 service-public.fr"

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

def get_bareme_saisie_via_ai() -> dict | None:
    """
    Orchestre la recherche Google et l'extraction par IA du barème de saisie sur salaire.
    """
    # --- 1. Construction du prompt demandant un JSON structuré avec calcul ---
    prompt_template = """
    Analyse le texte suivant et extrais les informations sur la saisie sur salaire pour 2025.
    Je veux deux choses :
    1. Le montant du "Solde Bancaire Insaisissable" (SBI).
    2. Le barème de saisie sur salaire COMPLET.

    Retourne le résultat dans un objet JSON valide et minifié.
    Pour le barème, la clé "quotite_saisissable" DOIT être la conversion de la fraction en nombre décimal (ex: "1/20" devient 0.05, "1/10" devient 0.1, "Totalité" devient 1.0).

    Le format doit être EXACTEMENT comme suit :
    {"sbi":635.71,"bareme":[{"tranche_plafond":4370.00,"quotite_saisissable":0.05},{"tranche_plafond":8520.00,"quotite_saisissable":0.10},{"tranche_plafond":12690.00,"quotite_saisissable":0.15},{"tranche_plafond":16850.00,"quotite_saisissable":0.20},{"tranche_plafond":21030.00,"quotite_saisissable":0.25},{"tranche_plafond":25280.00,"quotite_saisissable":0.3333},{"tranche_plafond":999999.99,"quotite_saisissable":1.0}]}

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

            if data and all(key in data for key in ["sbi", "bareme"]) and isinstance(data["bareme"], list) and len(data["bareme"]) > 1:
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
    Fonction adaptée de celle du script original.
    """
    try:
        with open(FICHIER_ENTREPRISE, 'r', encoding='utf-8') as f:
            config = json.load(f)
        
        saisie_config = config['PARAMETRES_ENTREPRISE']['constantes_paie_2025']['saisie_sur_salaire']
        
        print("\nMise à jour du fichier de configuration...")
        saisie_config['solde_bancaire_insaisissable'] = nouvelles_valeurs['sbi']
        saisie_config['bareme_mensuel'] = nouvelles_valeurs['bareme']
        
        with open(FICHIER_ENTREPRISE, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
            
        print(f"✅ Le fichier '{FICHIER_ENTREPRISE}' a été mis à jour avec succès.")
        
    except Exception as e:
        print(f"ERREUR : Une erreur est survenue lors de la mise à jour : {e}")

if __name__ == "__main__":
    valeurs = get_bareme_saisie_via_ai()
    
    if valeurs is not None:
        update_config_file(valeurs)