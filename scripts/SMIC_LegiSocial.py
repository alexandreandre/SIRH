# ATTENTION, ERREUR SUR LE SITE LEGISOCIAL





# # # scripts/SMIC_LegiSocial.py

# import json
# import re
# import requests
# from bs4 import BeautifulSoup

# # --- Fichiers et URL cibles ---
# FICHIER_ENTREPRISE = 'config/parametres_entreprise.json'
# URL_LEGISOCIAL = "https://www.legisocial.fr/reperes-sociaux/calcul-salaire-smic-2025.html"

# def parse_valeur_numerique(text: str) -> float:
#     """Nettoie et convertit un texte en nombre (float)."""
#     if not text: return 0.0
#     cleaned = text.replace('€', '').replace('\xa0', '').replace(' ', '').replace(',', '.')
#     match = re.search(r"([0-9]+\.?[0-9]*)", cleaned)
#     return float(match.group(1)) if match else 0.0

# def get_smic_legisocial() -> dict | None:
#     """
#     Scrape le site LegiSocial pour trouver la valeur du SMIC horaire.
#     """
#     try:
#         print(f"Scraping de l'URL : {URL_LEGISOCIAL}...")
#         response = requests.get(URL_LEGISOCIAL, timeout=20, headers={
#             "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.0.0 Safari/537.36"
#         })
#         response.raise_for_status()
#         soup = BeautifulSoup(response.text, "html.parser")

#         # On récupère tout le texte de la page pour y chercher la phrase clé
#         page_text = soup.get_text(" ", strip=True)
        
#         # Regex pour trouver la phrase et capturer les valeurs
#         motif = re.search(r"smic horaire est fixé à ([0-9,]+)\s*euros brut dans le cas général", page_text, re.IGNORECASE)
        
#         if not motif:
#             raise ValueError("Impossible de trouver la phrase contenant la valeur du SMIC sur la page.")
            
#         smic_general_str = motif.group(1)
#         smic_general = parse_valeur_numerique(smic_general_str)
        
#         print(f"  - SMIC horaire (cas général) trouvé : {smic_general} €")
        
#         return {"cas_general": smic_general}

#     except Exception as e:
#         print(f"ERREUR : Le scraping a échoué. Raison : {e}")
#         return None

# def update_config_file(nouveaux_smic: dict):
#     """
#     Met à jour le fichier de configuration avec les nouvelles valeurs du SMIC.
#     """
#     try:
#         with open(FICHIER_ENTREPRISE, 'r', encoding='utf-8') as f:
#             config = json.load(f)
        
#         smic_config = config['PARAMETRES_ENTREPRISE']['constantes_paie_2025']['smic_horaire']
        
#         # On ne met à jour que les clés trouvées pour ne pas écraser les autres
#         updated_count = 0
#         for key, value in nouveaux_smic.items():
#             if key in smic_config and smic_config[key] != value:
#                 print(f"Mise à jour du SMIC horaire ('{key}') : {smic_config[key]} -> {value}")
#                 smic_config[key] = value
#                 updated_count += 1
        
#         if updated_count == 0:
#             print("Les valeurs du SMIC dans le fichier de configuration sont déjà à jour.")
#             return

#         with open(FICHIER_ENTREPRISE, 'w', encoding='utf-8') as f:
#             json.dump(config, f, indent=2, ensure_ascii=False)
            
#         print(f"✅ Le fichier '{FICHIER_ENTREPRISE}' a été mis à jour avec succès.")
        
#     except Exception as e:
#         print(f"ERREUR : Une erreur est survenue lors de la mise à jour : {e}")


# if __name__ == "__main__":
#     valeurs = get_smic_legisocial()
    
#     if valeurs:
#         update_config_file(valeurs)