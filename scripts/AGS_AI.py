# scripts/AGS_AI.py

import json
import os
import requests
from bs4 import BeautifulSoup
from openai import OpenAI
from googlesearch import search
from dotenv import load_dotenv
load_dotenv()
# --- Fichiers de configuration (identiques à l'original) ---
FICHIER_ENTREPRISE = 'config/parametres_entreprise.json'
FICHIER_TAUX = 'config/taux_cotisations.json'
SEARCH_QUERY = "taux cotisation AGS actuel"

def extract_value_with_gpt(page_text: str, prompt: str) -> str | None:
    """
    Fonction générique pour interroger GPT-4o-mini avec un prompt et un texte donnés.
    """
    if not os.getenv("OPENAI_API_KEY"):
        print("ERREUR : La variable d'environnement OPENAI_API_KEY n'est pas définie.")
        return None
    try:
        client = OpenAI()
        print("Envoi de la requête à l'API GPT-4o-mini pour extraction...")
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
        print(f"Réponse brute de l'API : '{extracted_text}'")
        return extracted_text
    except Exception as e:
        print(f"ERREUR : L'appel à l'API OpenAI a échoué. Raison : {e}")
        return None

def get_taux_ags_via_ai(is_ett: bool) -> float | None:
    """
    Orchestre la recherche Google et l'extraction par IA pour trouver le taux AGS.
    """
    try:
        # --- 1. Construction du prompt en fonction du cas ---
        if is_ett:
            cas_specifique = "pour les entreprises de travail temporaire (ETT)."
        else:
            cas_specifique = "pour le cas général (hors entreprises de travail temporaire)."

        prompt = f"""
        Analyse le texte suivant et trouve le taux de la "Cotisation AGS" {cas_specifique}

        Réponds UNIQUEMENT avec le taux en pourcentage sous forme de nombre à virgule, en utilisant un point comme séparateur décimal.
        
        Exemple de réponse attendue : 0.15
        
        Si tu ne trouves pas la valeur, réponds "None".

        Voici le texte :
        ---
        """

        # --- 2. Recherche Google et récupération du texte ---
        print(f"Lancement de la recherche Google : '{SEARCH_QUERY}'...")
        search_results = list(search(SEARCH_QUERY, num_results=1, lang="fr"))
        if not search_results:
            raise ValueError("La recherche Google n'a retourné aucun résultat.")
        
        page_url = search_results[0]
        print(f"Page pertinente trouvée : {page_url}")

        response = requests.get(page_url, timeout=20, headers={'User-Agent': 'Mozilla/5.0'})
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        page_text = soup.get_text(" ", strip=True)
        
        # --- 3. Appel à l'IA et traitement de la réponse ---
        final_prompt = prompt + page_text[:12000]
        extracted_text = extract_value_with_gpt(page_text, final_prompt)

        if not extracted_text or extracted_text.lower() == 'none':
            raise ValueError("L'IA n'a pas pu extraire de valeur.")

        # Conversion en float et division par 100 pour obtenir le taux réel
        taux_percent = float(extracted_text.replace(',', '.'))
        taux_final = round(taux_percent / 100.0, 5)
        
        print(f" Taux final calculé : {taux_final*100:.2f}%")
        return taux_final

    except Exception as e:
        print(f"ERREUR : Le processus global a échoué. Raison : {e}")
        return None

def update_config_file(nouveau_taux: float):
    """
    Cette fonction est identique à celle du script original.
    """
    try:
        with open(FICHIER_TAUX, 'r', encoding='utf-8') as f:
            config = json.load(f)
        cotisation = config['TAUX_COTISATIONS']['ags']
        ancien_taux = cotisation['patronal']
        if ancien_taux == nouveau_taux:
            print(f"Le taux AGS dans '{FICHIER_TAUX}' est déjà correct ({nouveau_taux}).")
            return
        print(f"Mise à jour du taux AGS (patronal) : {ancien_taux} -> {nouveau_taux}")
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
        est_ett = conditions.get('est_entreprise_travail_temporaire', False)

        # On appelle notre nouvelle fonction IA
        taux = get_taux_ags_via_ai(is_ett=est_ett)
    
        if taux is not None:
            update_config_file(taux)

    except Exception as e:
        print(f"ERREUR : Le script principal a échoué : {e}")