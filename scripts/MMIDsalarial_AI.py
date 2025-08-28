# scripts/MMIDsalarial_AI.py

import json
import os
import requests
from bs4 import BeautifulSoup
from openai import OpenAI
from googlesearch import search
from dotenv import load_dotenv
load_dotenv()

# --- Fichiers de configuration ---
FICHIER_CONTRAT = 'config/parametres_contrat.json'
FICHIER_TAUX = 'config/taux_cotisations.json'
SEARCH_QUERY = "taux cotisation salariale maladie supplémentaire Alsace-Moselle URSSAF 2025"

def extract_value_with_gpt(page_text: str, prompt: str) -> str | None:
    """
    Fonction générique pour interroger GPT-4o-mini.
    """
    if not os.getenv("OPENAI_API_KEY"):
        print("ERREUR : La variable d'environnement OPENAI_API_KEY n'est pas définie.")
        return None
    try:
        client = OpenAI()
        print("   - Envoi de la requête à l'API GPT-4o-mini pour extraction...")
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
        print(f"   - Réponse brute de l'API : '{extracted_text}'")
        return extracted_text
    except Exception as e:
        print(f"   - ERREUR : L'appel à l'API OpenAI a échoué. Raison : {e}")
        return None

def get_taux_alsace_moselle_via_ai() -> float | None:
    """
    Orchestre la recherche Google et l'extraction par IA pour trouver le taux spécifique à l'Alsace-Moselle.
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

            final_prompt = prompt_template + page_text[:12000]
            extracted_text = extract_value_with_gpt(page_text, final_prompt)

            if extracted_text and extracted_text.lower() != 'none':
                taux_percent = float(extracted_text.replace(',', '.'))
                taux_final = round(taux_percent / 100.0, 5)
                print(f"✅ Valeur trouvée et validée ! Taux : {taux_final*100:.2f}%")
                return taux_final
            else:
                print("   - Aucune valeur extraite de cette page, passage à la suivante.")
        except Exception as e:
            print(f"   - ERREUR inattendue : {e}. Passage à la page suivante.")

    print("\n❌ ERREUR FATALE : Aucune valeur n'a pu être extraite après avoir essayé toutes les pages.")
    return None

def ajuster_taux_salarial_maladie_via_ai():
    """
    Lit le paramètre isAlsaceMoselle, utilise l'IA si nécessaire, et met à jour le fichier de cotisations.
    """
    try:
        with open(FICHIER_CONTRAT, 'r', encoding='utf-8') as f:
            config_contrat = json.load(f)
        
        is_alsace_moselle = config_contrat['PARAMETRES_CONTRAT']['poste'].get('isAlsaceMoselle', False)

        taux_correct = 0.0 # Valeur par défaut pour le régime général
        if is_alsace_moselle:
            print(f"Régime Alsace-Moselle détecté. Lancement de la recherche du taux spécifique...")
            taux_specifique = get_taux_alsace_moselle_via_ai()
            if taux_specifique is None:
                print("Arrêt du script car le taux spécifique n'a pas pu être récupéré.")
                return
            taux_correct = taux_specifique
        else:
            print("Régime général détecté. Le taux salarial maladie est de 0%.")

        with open(FICHIER_TAUX, 'r', encoding='utf-8') as f:
            config_taux = json.load(f)

        cotisation_maladie = config_taux['TAUX_COTISATIONS']['securite_sociale_maladie']
        taux_actuel = cotisation_maladie['salarial']
        
        if taux_actuel == taux_correct:
            print(f"Le taux salarial maladie dans '{FICHIER_TAUX}' est déjà correct ({taux_correct}).")
            return

        print(f"Mise à jour du taux salarial maladie : {taux_actuel} -> {taux_correct}")
        cotisation_maladie['salarial'] = taux_correct

        with open(FICHIER_TAUX, 'w', encoding='utf-8') as f:
            json.dump(config_taux, f, indent=2, ensure_ascii=False)
        print(f"✅ Le fichier '{FICHIER_TAUX}' a été mis à jour avec succès.")

    except FileNotFoundError as e:
        print(f"ERREUR : Le fichier '{e.filename}' est introuvable.")
    except Exception as e:
        print(f"ERREUR : Une erreur inattendue est survenue : {e}")

if __name__ == "__main__":
    ajuster_taux_salarial_maladie_via_ai()