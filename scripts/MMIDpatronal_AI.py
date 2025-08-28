# scripts/MMIDpatronal_AI.py

import json
import os
import requests
from bs4 import BeautifulSoup
from openai import OpenAI
from googlesearch import search

# --- Fichiers de configuration ---
FICHIER_ENTREPRISE = 'config/parametres_entreprise.json'
FICHIER_TAUX = 'config/taux_cotisations.json'
SEARCH_QUERY = "taux cotisation assurance maladie patronal urssaf 2025"

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

def get_taux_maladie_via_ai(is_taux_reduit: bool) -> float | None:
    """
    Orchestre la recherche Google et l'extraction par IA pour trouver le taux d'assurance maladie patronal.
    """
    # --- 1. Construction du prompt en fonction du cas ---
    if is_taux_reduit:
        cas_specifique = "le taux réduit (généralement pour les salaires sous 2,5 Smic)."
        print("Recherche du taux d'assurance maladie patronal : 'réduit'")
    else:
        cas_specifique = "le taux plein (ou taux de droit commun)."
        print("Recherche du taux d'assurance maladie patronal : 'plein'")

    prompt_template = f"""
    Analyse le texte suivant et trouve le taux de la cotisation patronale "Assurance maladie".
    Je cherche spécifiquement {cas_specifique}

    Réponds UNIQUEMENT avec le taux en pourcentage sous forme de nombre à virgule, en utilisant un point comme séparateur décimal.
    
    Exemple de réponse attendue : 7.00
    
    Si tu ne trouves pas la valeur exacte, réponds "None".

    Voici le texte :
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

def update_config_file(nouveau_taux: float):
    """
    Fonction identique à celle du script original.
    """
    try:
        with open(FICHIER_TAUX, 'r', encoding='utf-8') as f:
            config = json.load(f)
        cotisation = config['TAUX_COTISATIONS']['securite_sociale_maladie']
        ancien_taux = cotisation['patronal']
        if ancien_taux == nouveau_taux:
            print(f"Le taux dans '{FICHIER_TAUX}' est déjà correct ({nouveau_taux}). Aucune modification.")
            return
        print(f"Mise à jour du taux d'assurance maladie (patronal) : {ancien_taux} -> {nouveau_taux}")
        cotisation['patronal'] = nouveau_taux
        with open(FICHIER_TAUX, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        print(f"✅ Le fichier '{FICHIER_TAUX}' a été mis à jour avec succès.")
    except Exception as e:
        print(f"ERREUR : Une erreur est survenue lors de la mise à jour : {e}")


if __name__ == "__main__":
    # La logique de départ est identique à celle du script original
    try:
        with open(FICHIER_ENTREPRISE, 'r', encoding='utf-8') as f:
            config_entreprise = json.load(f)
        
        conditions = config_entreprise['PARAMETRES_ENTREPRISE']['conditions_cotisations']
        appliquer_taux_reduit = conditions.get('remuneration_annuelle_brute_inferieure_3.5_smic', False)

        taux = get_taux_maladie_via_ai(is_taux_reduit=appliquer_taux_reduit)
    
        if taux is not None:
            update_config_file(taux)

    except Exception as e:
        print(f"ERREUR : Le script principal a échoué : {e}")