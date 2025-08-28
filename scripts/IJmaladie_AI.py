# scripts/IJmaladieAI.py (version corrigée avec 50 tentatives)

import json
import requests
import os
from bs4 import BeautifulSoup
from openai import OpenAI
from googlesearch import search

FICHIER_BAREMES = 'config/baremes.json'
# On utilise l'année en cours pour une recherche plus précise
SEARCH_QUERY = "montant maximum indemnité journalière maladie actuel"

def extract_value_with_gpt(page_text: str) -> float | None:
    """
    Utilise l'API OpenAI (GPT) pour extraire le plafond IJSS du texte d'une page.
    """
    if not os.getenv("OPENAI_API_KEY"):
        print("   - ERREUR : La variable d'environnement OPENAI_API_KEY n'est pas définie.")
        return None

    try:
        client = OpenAI()
        prompt = f"""
        Tu es un expert en extraction de données financières. Analyse le texte suivant et identifie le montant maximum de l'indemnité journalière maladie de base.
        La valeur que je cherche est un montant JOURNALIER, généralement entre 40 et 60 euros. Ignore les autres montants.
        Pour 2025, choisis la valeur applicable après le 1er avril 2025.
        Réponds UNIQUEMENT avec le nombre, en utilisant un point comme séparateur décimal.
        Exemple de réponse : 41.47
        Si tu ne trouves pas ce montant spécifique, réponds "None".
        Voici le texte :
        ---
        {page_text[:12000]}
        """

        print("   - Envoi de la requête à l'API GPT pour extraction...")
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "Tu es un expert en extraction de données précises."},
                {"role": "user", "content": prompt}
            ],
            temperature=0,
            max_tokens=10
        )
        
        extracted_text = response.choices[0].message.content.strip()
        print(f"   - Réponse brute de l'API : '{extracted_text}'")
        
        if extracted_text.lower() == 'none' or not extracted_text:
            return None
        
        # Nettoyage robuste du nombre avant conversion
        cleaned_text = extracted_text.replace('.', '', extracted_text.count('.') - 1).replace(',', '.')
        return float(cleaned_text)

    except Exception as e:
        print(f"   - ERREUR pendant l'extraction IA : {e}")
        return None

def get_plafond_ij_via_recherche_et_gpt() -> float | None:
    """
    Cherche sur Google et essaie jusqu'à 50 pages pour trouver une valeur valide.
    """
    print(f"Lancement de la recherche Google : '{SEARCH_QUERY}'...")
    # MODIFIÉ : On cherche 50 résultats au lieu d'un seul
    try:
        search_results = list(search(SEARCH_QUERY, num_results=50, lang="fr"))
    except Exception as e:
        print(f"ERREUR lors de la recherche Google : {e}")
        return None

    if not search_results:
        print("ERREUR : La recherche Google n'a retourné aucun résultat.")
        return None

    # NOUVEAU : On boucle sur chaque résultat trouvé
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

            valeur = extract_value_with_gpt(page_text)
            if valeur is not None:
                print(f"✅ Valeur trouvée et validée sur cette page !")
                return valeur # On a trouvé, on arrête et on renvoie la valeur
            else:
                print("   - Aucune valeur extraite de cette page, passage à la suivante.")

        except Exception as e:
            print(f"   - ERREUR lors du traitement de la page : {e}. Passage à la suivante.")

    # Si on sort de la boucle sans avoir trouvé de valeur
    print(f"\n❌ ERREUR FATALE : Aucune valeur n'a pu être extraite après avoir essayé {len(search_results)} pages.")
    return None

def update_config_file(nouveau_plafond: float):
    # Cette fonction reste inchangée
    try:
        with open(FICHIER_BAREMES, 'r', encoding='utf-8') as f:
            config = json.load(f)
        ij_config = config['SECURITE_SOCIALE_2025']['indemnites_journalieres_maladie']
        if ij_config.get('plafond_ij_base') == nouveau_plafond:
            print(f"\nLe plafond IJSS dans '{FICHIER_BAREMES}' est déjà à jour ({nouveau_plafond} €).")
            return
        print(f"\nMise à jour du plafond IJSS : {ij_config.get('plafond_ij_base')} -> {nouveau_plafond}")
        ij_config['plafond_ij_base'] = nouveau_plafond
        with open(FICHIER_BAREMES, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        print(f"✅ Le fichier '{FICHIER_BAREMES}' a été mis à jour avec succès.")
    except Exception as e:
        print(f"\nERREUR : Une erreur est survenue lors de la mise à jour : {e}")

if __name__ == "__main__":
    valeur = get_plafond_ij_via_recherche_et_gpt()
    if valeur is not None:
        update_config_file(valeur)