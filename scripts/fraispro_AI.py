# scripts/fraispro_AI.py

import json
import os
import requests
from bs4 import BeautifulSoup
from openai import OpenAI
from googlesearch import search

# --- Fichiers de configuration ---
FICHIER_BAREMES = 'config/baremes.json'
SEARCH_QUERY = "barèmes frais professionnels URSSAF 2025"

def extract_json_with_gpt(page_text: str, prompt: str) -> dict | None:
    """
    Interroge GPT-4o-mini et s'attend à recevoir une chaîne de caractères JSON valide.
    """
    if not os.getenv("OPENAI_API_KEY"):
        print("ERREUR : La variable d'environnement OPENAI_API_KEY n'est pas définie.")
        return None
    try:
        client = OpenAI()
        print("   - Envoi de la requête à l'API GPT-4o-mini pour extraction JSON (requête complexe)...")
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": "Tu es un expert en extraction de données complexes qui répond au format JSON."},
                {"role": "user", "content": prompt}
            ],
            temperature=0
        )
        extracted_text = response.choices[0].message.content.strip()
        print(f"   - Réponse brute de l'API (premiers 200 caractères): {extracted_text[:200]}...")
        return json.loads(extracted_text)
    except Exception as e:
        print(f"   - ERREUR : L'appel à l'API ou le parsing JSON a échoué. Raison : {e}")
        return None

def get_fraispro_via_ai() -> dict | None:
    """
    Orchestre la recherche Google et l'extraction JSON de l'ensemble des barèmes de frais professionnels.
    """
    # --- 1. Construction du prompt le plus détaillé possible ---
    prompt_template = """
    Analyse le texte suivant de la page URSSAF "Frais professionnels" pour 2025.
    Extrais TOUTES les informations des sections suivantes : Repas, Petit déplacement, Grand déplacement, Mutation professionnelle, Mobilité durable, et Télétravail.
    Tu DOIS retourner un unique objet JSON minifié avec une clé racine "FRAIS_PROFESSIONNELS_2025".
    La structure interne doit EXACTEMENT correspondre à cet exemple. Sois très attentif aux noms des clés et à la structure des listes et des objets.
    
    Exemple de format attendu :
    {"FRAIS_PROFESSIONNELS_2025":{"repas_indemnites":{"sur_lieu_travail":7.30,"hors_locaux_sans_restaurant":10.10,"hors_locaux_avec_restaurant":20.70},"petit_deplacement_bareme":[{"km_min":5,"km_max":20,"montant":3.10}],"grand_deplacement":{"metropole":[{"periode_sejour":"3 premiers mois","repas":20.70,"logement_paris_banlieue":74.30,"logement_province":55.10}],"outre_mer_groupe1":[],"outre_mer_groupe2":[]},"mutation_professionnelle":{"hebergement_provisoire":{"montant_par_jour":80.10},"hebergement_definitif":{"frais_installation":1613.00,"majoration_par_enfant":134.40,"plafond_total":3224.00}},"mobilite_durable":{"employeurs_prives":{"limite_base":700,"limite_cumul_transport_public":800}},"teletravail":{"indemnite_sans_accord":{"par_jour":2.70,"limite_mensuelle":59.40,"par_mois_pour_1_jour_semaine":10.70},"indemnite_avec_accord":{"par_jour":3.25,"limite_mensuelle":71.50},"materiel_informatique_perso":{"montant_mensuel":50.00}}}}

    Voici le texte à analyser :
    ---
    """

    # --- 2. Boucle sur les résultats de recherche ---
    print(f"Lancement de la recherche Google : '{SEARCH_QUERY}'...")
    search_results = list(search(SEARCH_QUERY, num_results=50, lang="fr"))
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

            final_prompt = prompt_template + page_text
            data = extract_json_with_gpt(page_text, final_prompt)

            # Validation robuste de la structure retournée
            if (data and "FRAIS_PROFESSIONNELS_2025" in data and
                    all(key in data["FRAIS_PROFESSIONNELS_2025"] for key in 
                        ["repas_indemnites", "petit_deplacement_bareme", "grand_deplacement",
                         "mutation_professionnelle", "mobilite_durable", "teletravail"])):
                print(f"✅ JSON valide et complet extrait de la page !")
                return data["FRAIS_PROFESSIONNELS_2025"]
            else:
                print("   - Le JSON extrait est incomplet ou invalide, passage à la page suivante.")

        except Exception as e:
            print(f"   - ERREUR inattendue : {e}. Passage à la page suivante.")

    print("\n❌ ERREUR FATALE : Aucune donnée valide n'a pu être extraite.")
    return None

def update_config_file(nouveaux_baremes: dict):
    """
    Met à jour le fichier baremes.json avec l'ensemble des nouveaux barèmes.
    """
    try:
        with open(FICHIER_BAREMES, 'r', encoding='utf-8') as f:
            config = json.load(f)
        
        print("\nMise à jour du fichier de configuration...")
        
        # On remplace l'intégralité de l'objet des frais professionnels
        config['FRAIS_PROFESSIONNELS_2025'] = nouveaux_baremes
        
        with open(FICHIER_BAREMES, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
            
        print(f"✅ Le fichier '{FICHIER_BAREMES}' a été mis à jour avec succès.")

    except Exception as e:
        print(f"ERREUR : Une erreur est survenue lors de la mise à jour : {e}")

if __name__ == "__main__":
    baremes = get_fraispro_via_ai()
    
    if baremes is not None:
        update_config_file(baremes)