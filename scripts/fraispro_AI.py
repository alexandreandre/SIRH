# scripts/fraispro_AI.py

import json
import os
import requests
from bs4 import BeautifulSoup
from openai import OpenAI
from googlesearch import search
from dotenv import load_dotenv
load_dotenv()

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
                {"role": "system", "content": "Tu es un assistant expert en extraction de données qui répond au format JSON de manière stricte."},
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
    # --- PROMPT AMÉLIORÉ AVEC STRUCTURE STRICTE ---
    prompt_template = """
    Analyse le texte suivant de la page URSSAF "Frais professionnels" pour 2025.
    Ton objectif est d'extraire TOUTES les valeurs numériques pour remplir la structure JSON ci-dessous.

    RÈGLES STRICTES :
    1.  Tu DOIS retourner un unique objet JSON avec une clé racine "FRAIS_PROFESSIONNELS_2025".
    2.  La structure interne doit EXACTEMENT correspondre à l'exemple. Ne change aucun nom de clé.
    3.  Si une section ou une valeur spécifique N'EST PAS PRÉSENTE dans le texte, tu DOIS quand même inclure la clé dans le JSON, en lui laissant sa valeur par défaut (0, [], ou un objet avec des 0). NE PAS OMETTRE de clés.
    4.  Réponds UNIQUEMENT avec l'objet JSON, sans aucun texte ou explication avant ou après.

    Voici la structure à remplir :
    ```json
    {
      "FRAIS_PROFESSIONNELS_2025": {
        "repas_indemnites": {
          "sur_lieu_travail": 0,
          "hors_locaux_avec_restaurant": 0,
          "hors_locaux_sans_restaurant": 0
        },
        "petit_deplacement_bareme": [],
        "grand_deplacement": {
          "metropole": [],
          "outre_mer_groupe1": [],
          "outre_mer_groupe2": []
        },
        "mutation_professionnelle": {
          "hebergement_provisoire": {
            "montant_par_jour": 0
          },
          "hebergement_definitif": {
            "frais_installation": 0,
            "majoration_par_enfant": 0,
            "plafond_total": 0
          }
        },
        "mobilite_durable": {
          "employeurs_prives": {
            "limite_base": 0,
            "limite_cumul_transport_public": 0
          }
        },
        "teletravail": {
          "indemnite_sans_accord": {
            "par_jour": 0,
            "limite_mensuelle": 0,
            "par_mois_pour_1_jour_semaine": 0
          }
        }
      }
    }
    ```

    Voici le texte à analyser :
    ---
    """

    # --- Boucle sur les résultats de recherche ---
    print(f"Lancement de la recherche Google : '{SEARCH_QUERY}'...")
    # On limite à 5 tentatives, car les premières pages sont généralement les plus pertinentes.
    search_results = list(search(SEARCH_QUERY, num_results=5, lang="fr"))
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

            # Validation simple pour s'assurer que la clé racine est présente
            if data and "FRAIS_PROFESSIONNELS_2025" in data:
                print(f"✅ JSON avec la structure racine correcte extrait de la page !")
                return data["FRAIS_PROFESSIONNELS_2025"]
            else:
                print("   - Le JSON extrait n'a pas la bonne structure racine, passage à la page suivante.")

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