# scripts/IJmaladieAI.py

import json
import requests
import os
from bs4 import BeautifulSoup
from openai import OpenAI
from googlesearch import search
from dotenv import load_dotenv
load_dotenv()

# --- Fichiers et URL cibles ---
FICHIER_BAREMES = 'config/baremes.json'
SEARCH_QUERY = "montants maximum indemnités journalières ameli 2025"

def extract_json_with_gpt(page_text: str) -> dict | None:
    """
    Interroge GPT-4o-mini et s'attend à recevoir une chaîne de caractères JSON valide
    contenant les quatre plafonds d'indemnités.
    """
    if not os.getenv("OPENAI_API_KEY"):
        print("   - ERREUR : La variable d'environnement OPENAI_API_KEY n'est pas définie.")
        return None

    try:
        client = OpenAI()
        # On définit un prompt qui demande un JSON structuré
        prompt = f"""
        Analyse le texte suivant et extrais les 4 montants maximums des indemnités journalières pour 2025.
        Les clés doivent être "maladie", "maternite_paternite", "at_mp", et "at_mp_majoree".
        Les valeurs doivent être des nombres.

        Le format de sortie DOIT être un JSON minifié. Ne fournis AUCUNE explication.
        
        Exemple de format attendu :
        {{"maladie":41.47,"maternite_paternite":101.94,"at_mp":235.69,"at_mp_majoree":314.25}}

        Voici le texte :
        ---
        {page_text[:12000]}
        """

        print("   - Envoi de la requête à l'API GPT pour extraction JSON...")
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
        print(f"   - Réponse brute de l'API : '{extracted_text}'")
        
        # On parse la chaîne de caractères en objet Python
        return json.loads(extracted_text)

    except Exception as e:
        print(f"   - ERREUR pendant l'extraction IA : {e}")
        return None

def get_all_plafonds_ij_via_ai() -> dict | None:
    """
    Cherche sur Google et essaie jusqu'à 50 pages pour trouver les valeurs valides.
    """
    print(f"Lancement de la recherche Google : '{SEARCH_QUERY}'...")
    try:
        search_results = list(search(SEARCH_QUERY, num_results=50, lang="fr"))
    except Exception as e:
        print(f"ERREUR lors de la recherche Google : {e}")
        return None

    if not search_results:
        print("ERREUR : La recherche Google n'a retourné aucun résultat.")
        return None

    for i, page_url in enumerate(search_results):
        print(f"\n--- Tentative {i+1}/{len(search_results)} sur la page : {page_url} ---")
        try:
            response = requests.get(page_url, timeout=15, headers={'User-Agent': 'Mozilla/5.0'})
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")
            page_text = soup.get_text(" ", strip=True)

            if not page_text.strip():
                print("   - Page vide, passage à la suivante.")
                continue

            data = extract_json_with_gpt(page_text)
            
            # Validation pour s'assurer que le JSON est complet
            expected_keys = ["maladie", "maternite_paternite", "at_mp", "at_mp_majoree"]
            if data and all(key in data for key in expected_keys):
                print(f"✅ JSON valide et complet extrait de la page !")
                return data
            else:
                print("   - Le JSON extrait est incomplet ou invalide, passage à la page suivante.")

        except Exception as e:
            print(f"   - ERREUR lors du traitement de la page : {e}. Passage à la suivante.")

    print(f"\n❌ ERREUR FATALE : Aucune donnée valide n'a pu être extraite après avoir essayé {len(search_results)} pages.")
    return None

def update_config_file(nouveaux_plafonds: dict):
    """
    Met à jour le fichier baremes.json avec toutes les nouvelles valeurs.
    """
    try:
        with open(FICHIER_BAREMES, 'r', encoding='utf-8') as f:
            config = json.load(f)
        
        # On utilise la même structure que le script Selenium
        ij_config = config.setdefault('SECURITE_SOCIALE_2025', {}).setdefault('plafonds_indemnites_journalieres', {})
        
        if 'indemnites_journalieres_maladie' in config['SECURITE_SOCIALE_2025']:
            del config['SECURITE_SOCIALE_2025']['indemnites_journalieres_maladie']

        print("\nMise à jour du fichier de configuration...")
        ij_config.update(nouveaux_plafonds)
        
        with open(FICHIER_BAREMES, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
            
        print(f"✅ Le fichier '{FICHIER_BAREMES}' a été mis à jour avec succès.")
        
    except Exception as e:
        print(f"\nERREUR : Une erreur est survenue lors de la mise à jour : {e}")

if __name__ == "__main__":
    valeurs = get_all_plafonds_ij_via_ai()
    if valeurs is not None:
        update_config_file(valeurs)