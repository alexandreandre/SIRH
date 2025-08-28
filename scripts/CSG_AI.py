# scripts/CSG_AI.py

import json
import os
import requests
from bs4 import BeautifulSoup
from openai import OpenAI
from googlesearch import search
from dotenv import load_dotenv
load_dotenv()

# --- Fichiers de configuration ---
FICHIER_TAUX = 'config/taux_cotisations.json'
SEARCH_QUERY = "taux csg crds salarié urssaf 2025"

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

def get_taux_csg_crds_via_ai() -> dict | None:
    """
    Orchestre la recherche Google, l'extraction par IA et le calcul final des taux.
    """
    # --- 1. Construction du prompt demandant les 3 taux bruts ---
    prompt_template = """
    Analyse le texte suivant de la section "Taux de cotisations salarié" et extrais les 3 taux suivants :
    1. Le taux de la "CSG imposable".
    2. Le taux de la "CSG non imposable" (qui est la part déductible).
    3. Le taux de la "CRDS".

    Retourne le résultat dans un objet JSON valide et minifié.
    Les clés doivent être "csg_imposable", "csg_non_imposable", "crds".

    Ne fournis AUCUNE explication, juste le JSON. Le format doit être EXACTEMENT comme suit :
    {"csg_imposable":2.40,"csg_non_imposable":6.80,"crds":0.50}

    Voici le texte à analyser :
    ---
    """

    # --- 2. Boucle sur les résultats de recherche ---
    print(f"Lancement de la recherche Google : '{SEARCH_QUERY}'...")
    search_results = list(search(SEARCH_QUERY, num_results=50, lang="fr"))
    if not search_results:
        print("ERREUR : La recherche Google n'a retourné aucun résultat.")
        return None

    taux_bruts = None
    for i, page_url in enumerate(search_results):
        print(f"\n--- Tentative {i+1}/3 sur la page : {page_url} ---")
        try:
            response = requests.get(page_url, timeout=20, headers={'User-Agent': 'Mozilla/5.0'})
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")
            page_text = soup.get_text(" ", strip=True)

            final_prompt = prompt_template + page_text[:12000]
            data = extract_json_with_gpt(page_text, final_prompt)

            if data and all(key in data for key in ["csg_imposable", "csg_non_imposable", "crds"]):
                print(f"✅ JSON valide et complet extrait de la page !")
                taux_bruts = data
                break # On a trouvé, on sort de la boucle
            else:
                print("   - Le JSON extrait est incomplet ou invalide, passage à la page suivante.")
        except Exception as e:
            print(f"   - ERREUR inattendue : {e}. Passage à la page suivante.")

    # --- 3. Calcul final si les données ont été extraites ---
    if taux_bruts:
        taux_deductible = round(taux_bruts["csg_non_imposable"] / 100.0, 5)
        taux_non_deductible_brut = taux_bruts["csg_imposable"] + taux_bruts["crds"]
        taux_non_deductible_final = round(taux_non_deductible_brut / 100.0, 5)

        print(f"\nCalcul final des taux :")
        print(f"  - Taux déductible : {taux_deductible*100:.2f}%")
        print(f"  - Taux non déductible : {taux_non_deductible_final*100:.2f}% (calculé depuis {taux_bruts['csg_imposable']}% + {taux_bruts['crds']}%)")

        return {"deductible": taux_deductible, "non_deductible": taux_non_deductible_final}

    print("\n❌ ERREUR FATALE : Aucune donnée valide n'a pu être extraite.")
    return None

def update_config_file(nouveaux_taux: dict):
    """
    Fonction identique à celle du script original.
    """
    try:
        with open(FICHIER_TAUX, 'r', encoding='utf-8') as f:
            config = json.load(f)
        cotisation_deductible = config['TAUX_COTISATIONS']['csg_deductible']
        cotisation_non_deductible = config['TAUX_COTISATIONS']['csg_crds_non_deductible']
        print(f"\nMise à jour de 'csg_deductible' (salarial) : {cotisation_deductible['salarial']} -> {nouveaux_taux['deductible']}")
        print(f"Mise à jour de 'csg_crds_non_deductible' (salarial) : {cotisation_non_deductible['salarial']} -> {nouveaux_taux['non_deductible']}")
        cotisation_deductible['salarial'] = nouveaux_taux['deductible']
        cotisation_non_deductible['salarial'] = nouveaux_taux['non_deductible']
        with open(FICHIER_TAUX, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        print(f"✅ Le fichier '{FICHIER_TAUX}' a été mis à jour avec succès.")
    except Exception as e:
        print(f"ERREUR : Une erreur est survenue lors de la mise à jour : {e}")

if __name__ == "__main__":
    taux = get_taux_csg_crds_via_ai()
    
    if taux is not None:
        update_config_file(taux)