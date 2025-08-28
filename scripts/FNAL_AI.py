# scripts/FNAL_AI.py

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
FICHIER_TAUX = 'config/taux_cotisations.json'
SEARCH_QUERY = "taux cotisation fnal urssaf 2025"

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

def get_taux_fnal_via_ai(is_effectif_inferieur_50: bool) -> float | None:
    """
    Orchestre la recherche Google et l'extraction par IA pour trouver le taux FNAL.
    """
    # --- 1. Construction du prompt en fonction de l'effectif ---
    if is_effectif_inferieur_50:
        cas_specifique = "pour les entreprises de MOINS de 50 salariés."
        print("Recherche du taux FNAL pour l'effectif : '< 50 salariés'")
    else:
        cas_specifique = "pour les entreprises de 50 salariés ET PLUS."
        print("Recherche du taux FNAL pour l'effectif : '>= 50 salariés'")

    prompt_template = f"""
    Analyse le texte suivant et trouve le taux de la cotisation "FNAL" (Fonds National d'Aide au Logement) applicable {cas_specifique}

    Réponds UNIQUEMENT avec le taux en pourcentage sous forme de nombre à virgule, en utilisant un point comme séparateur décimal.
    
    Exemple de réponse attendue : 0.10
    
    Si tu ne trouves pas la valeur, réponds "None".

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
        cotisation = config['TAUX_COTISATIONS']['fnal']
        ancien_taux = cotisation['patronal']
        if ancien_taux == nouveau_taux:
            print(f"Le taux FNAL dans '{FICHIER_TAUX}' est déjà correct ({nouveau_taux}).")
            return
        print(f"Mise à jour du taux FNAL (patronal) : {ancien_taux} -> {nouveau_taux}")
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
        effectif = conditions.get('effectif_total')
        
        if effectif is None:
            raise KeyError("La clé 'effectif_total' est manquante dans parametres_entreprise.json")

        est_inferieur_a_50 = (effectif < 50)
        
        # On appelle notre nouvelle fonction IA
        taux = get_taux_fnal_via_ai(is_effectif_inferieur_50=est_inferieur_a_50)
    
        if taux is not None:
            update_config_file(taux)

    except Exception as e:
        print(f"ERREUR : Le script principal a échoué : {e}")