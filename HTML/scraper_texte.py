# Étape 1 : Importer les bibliothèques nécessaires
import requests
from bs4 import BeautifulSoup

def extraire_texte_de_la_page(url):
    """
    Cette fonction prend une URL en entrée, télécharge le contenu de la page
    et en extrait tout le texte visible.
    """
    try:
        # Étape 2 : Envoyer une requête à l'URL pour obtenir le contenu de la page
        # L'en-tête 'User-Agent' aide à simuler un vrai navigateur
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
        reponse = requests.get(url, headers=headers, timeout=10)
        
        # Vérifier si la requête a réussi (code 200 OK)
        reponse.raise_for_status()
        
        # Étape 3 : Analyser le contenu HTML de la page avec Beautiful Soup
        soup = BeautifulSoup(reponse.content, 'html.parser')
        
        # Étape 4 : Extraire tout le texte du corps (body) de la page
        # .get_text() est la fonction magique qui fait tout le travail.
        # separator=' ' assure que les mots de différentes balises sont séparés par un espace.
        # strip=True retire les espaces inutiles en début et fin de chaque morceau de texte.
        texte_brut = soup.get_text(separator=' ', strip=True)
        
        return texte_brut

    except requests.exceptions.RequestException as e:
        # Gérer les erreurs de connexion, URL invalide, etc.
        print(f"Erreur lors de la requête vers l'URL : {e}")
        return None

# --- Point d'entrée du script ---
if __name__ == "__main__":
    # !! MODIFIEZ CETTE LIGNE AVEC L'URL QUE VOUS VOULEZ SCRAPER !!
    url_a_scraper = "https://www.legisocial.fr/modele-bulletin-paie/salarie-cadre-heures-supplementaires-structurelles-absence-maintenue-2025.html"
    
    print(f"Extraction du texte de l'URL : {url_a_scraper}\n")
    
    # Appel de la fonction pour extraire le texte
    texte_extrait = extraire_texte_de_la_page(url_a_scraper)
    
    # Afficher le résultat si l'extraction a fonctionné
    if texte_extrait:
        print("--- DÉBUT DU TEXTE EXTRAIT ---")
        print(texte_extrait)
        print("--- FIN DU TEXTE EXTRAIT ---")