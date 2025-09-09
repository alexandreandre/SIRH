# scripts/AGIRC-ARRCO_AI.py

import json
import os
import requests
from bs4 import BeautifulSoup
from openai import OpenAI
from googlesearch import search
from dotenv import load_dotenv
load_dotenv()
# --- Fichiers et URL cibles ---
FICHIER_TAUX = 'config/taux_cotisations.json'
SEARCH_QUERY = "agirc-arrco calcul des cotisations de retraite complémentaire 2025"

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
                {"role": "system", "content": "Tu es un expert en extraction de données qui répond au format JSON de manière stricte."},
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

def get_all_taux_agirc_arrco_via_ai() -> dict | None:
    """
    Orchestre la recherche Google et l'extraction par IA de tous les taux Agirc-Arrco.
    """
    # --- PROMPT DÉTAILLÉ POUR EXTRAIRE TOUTES LES VALEURS ---
    prompt_template = """
    Analyse le texte suivant de la page Agirc-Arrco sur les cotisations 2025.
    Extrais les taux de cotisation salariaux et patronaux pour les 6 catégories suivantes :
    1. Taux de cotisation pour la "Tranche 1".
    2. Taux de cotisation pour la "Tranche 2".
    3. Contribution d'équilibre général (CEG) pour la "Tranche 1".
    4. Contribution d'équilibre général (CEG) pour la "Tranche 2".
    5. Contribution d'équilibre technique (CET).
    6. Cotisation APEC.

    Retourne le résultat dans un unique objet JSON. Les valeurs doivent être les pourcentages (ex: pour 3,15 %, renvoie 3.15).
    Le format doit être EXACTEMENT comme suit :
    {
      "retraite_comp_t1_salarial": 3.15,
      "retraite_comp_t1_patronal": 4.72,
      "retraite_comp_t2_salarial": 8.64,
      "retraite_comp_t2_patronal": 12.95,
      "ceg_t1_salarial": 0.86,
      "ceg_t1_patronal": 1.29,
      "ceg_t2_salarial": 1.08,
      "ceg_t2_patronal": 1.62,
      "cet_salarial": 0.14,
      "cet_patronal": 0.21,
      "apec_salarial": 0.024,
      "apec_patronal": 0.036
    }

    Voici le texte à analyser :
    ---
    """

    # --- Boucle sur les résultats de recherche ---
    print(f"Lancement de la recherche Google : '{SEARCH_QUERY}'...")
    search_results = list(search(SEARCH_QUERY, num_results=50, lang="fr"))
    if not search_results:
        print("ERREUR : La recherche Google n'a retourné aucun résultat.")
        return None

    for i, page_url in enumerate(search_results):
        print(f"\n--- Tentative {i+1}/{len(search_results)} sur la page : {page_url} ---")
        try:
            response = requests.get(page_url, timeout=20, headers={'User-Agent': 'Mozilla/5.0'})
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")
            page_text = soup.get_text(" ", strip=True)

            final_prompt = prompt_template + page_text
            data = extract_json_with_gpt(page_text, final_prompt)

            expected_keys = [
                'retraite_comp_t1_salarial', 'retraite_comp_t1_patronal', 'retraite_comp_t2_salarial', 
                'retraite_comp_t2_patronal', 'ceg_t1_salarial', 'ceg_t1_patronal', 'ceg_t2_salarial', 
                'ceg_t2_patronal', 'cet_salarial', 'cet_patronal', 'apec_salarial', 'apec_patronal'
            ]
            if data and all(key in data for key in expected_keys):
                print(f"✅ JSON valide et complet extrait de la page !")
                # On convertit tous les pourcentages en taux réels
                taux_reels = {key: round(value / 100.0, 5) for key, value in data.items()}
                return taux_reels
            else:
                print("   - Le JSON extrait est incomplet ou invalide, passage à la page suivante.")

        except Exception as e:
            print(f"   - ERREUR inattendue : {e}. Passage à la page suivante.")

    print(f"\n❌ ERREUR FATALE : Aucune donnée valide n'a pu être extraite.")
    return None

def update_config_file(nouveaux_taux: dict):
    # Cette fonction est identique à celle du script PDF
    try:
        with open(FICHIER_TAUX, 'r', encoding='utf-8') as f:
            config = json.load(f)
        
        retraite_t1 = config['TAUX_COTISATIONS']['retraite_comp_t1']
        retraite_t2 = config['TAUX_COTISATIONS']['retraite_comp_t2']
        ceg_t1 = config['TAUX_COTISATIONS']['ceg_t1']
        ceg_t2 = config['TAUX_COTISATIONS']['ceg_t2']
        cet = config['TAUX_COTISATIONS']['cet']
        apec = config['TAUX_COTISATIONS']['apec']

        print("\nMise à jour du fichier de configuration...")
        retraite_t1.update({'salarial': nouveaux_taux['retraite_comp_t1_salarial'], 'patronal': nouveaux_taux['retraite_comp_t1_patronal']})
        retraite_t2.update({'salarial': nouveaux_taux['retraite_comp_t2_salarial'], 'patronal': nouveaux_taux['retraite_comp_t2_patronal']})
        ceg_t1.update({'salarial': nouveaux_taux['ceg_t1_salarial'], 'patronal': nouveaux_taux['ceg_t1_patronal']})
        ceg_t2.update({'salarial': nouveaux_taux['ceg_t2_salarial'], 'patronal': nouveaux_taux['ceg_t2_patronal']})
        cet.update({'salarial': nouveaux_taux['cet_salarial'], 'patronal': nouveaux_taux['cet_patronal']})
        apec.update({'salarial': nouveaux_taux['apec_salarial'], 'patronal': nouveaux_taux['apec_patronal']})
        
        with open(FICHIER_TAUX, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
            
        print(f"✅ Le fichier '{FICHIER_TAUX}' a été mis à jour avec succès.")
    except Exception as e:
        print(f"ERREUR : Une erreur est survenue lors de la mise à jour : {e}")

if __name__ == "__main__":
    extracted_taux = get_all_taux_agirc_arrco_via_ai()
    if extracted_taux:
        update_config_file(extracted_taux)