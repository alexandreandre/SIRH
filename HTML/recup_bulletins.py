import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import os
import time

def creer_dossier_si_necessaire(nom_dossier):
    """Crée un dossier s'il n'existe pas déjà."""
    if not os.path.exists(nom_dossier):
        os.makedirs(nom_dossier)
        print(f"📁 Dossier '{nom_dossier}' créé.")

def extraire_page_connectee(url, chemin_fichier_sortie, cookies_session):
    """
    Extrait le HTML et le CSS d'une page web en utilisant un cookie de session
    et sauvegarde le résultat dans un fichier HTML unique.

    Args:
        url (str): L'URL de la page web à traiter.
        chemin_fichier_sortie (str): Le chemin complet du fichier HTML de sortie.
        cookies_session (dict): Un dictionnaire contenant les cookies de session.
    
    Returns:
        bool: True si l'extraction a réussi, False sinon.
    """
    try:
        reponse = requests.get(url, cookies=cookies_session)
        reponse.raise_for_status()

        soup = BeautifulSoup(reponse.text, 'html.parser')

        # Trouver et intégrer les feuilles de style externes
        for lien in soup.find_all('link', rel='stylesheet'):
            href = lien.get('href')
            if href:
                url_css = urljoin(url, href)
                try:
                    css_reponse = requests.get(url_css, cookies=cookies_session)
                    css_reponse.raise_for_status()
                    style_tag = soup.new_tag('style')
                    style_tag.string = css_reponse.text
                    lien.replace_with(style_tag)
                except requests.exceptions.RequestException as e:
                    print(f"   ⚠️ Attention : Impossible de télécharger le CSS depuis {url_css}: {e}")

        # Sauvegarder le HTML modifié
        with open(chemin_fichier_sortie, 'w', encoding='utf-8') as f:
            f.write(str(soup))
            
        return True

    except requests.exceptions.RequestException as e:
        print(f"   ❌ Erreur lors du téléchargement de la page : {e}")
        return False

# --- CONFIGURATION ---
if __name__ == '__main__':
    # 1. Mettez ici la liste de toutes les URL que vous souhaitez sauvegarder.
    #    Ajoutez autant de liens que nécessaire.
    liste_des_liens = [
        "https://www.legisocial.fr/votre-page-bulletin-1",
        "https://www.legisocial.fr/votre-page-bulletin-2",
        "https://www.legisocial.fr/votre-page-bulletin-3",
        # "https://www.legisocial.fr/autre-page-exemple-4",
        # ...etc.
    ]

    # 2. Nom du dossier où seront sauvegardés les fichiers.
    dossier_de_sortie = "Bulletins_Exemples"

    # 3. Vos cookies de session.
    #    Assurez-vous que cette session est toujours active !
    vos_cookies = {
        'PHPSESSID': 'o8h8d358jtlii0vn6vof0a2vvf' 
    }

    # --- EXÉCUTION DU SCRIPT ---
    creer_dossier_si_necessaire(dossier_de_sortie)
    
    print(f"\n🚀 Démarrage de l'extraction de {len(liste_des_liens)} page(s)...")

    for index, lien in enumerate(liste_des_liens):
        numero_bulletin = index + 1
        nom_fichier = f"bulletin_{numero_bulletin}.html"
        chemin_complet = os.path.join(dossier_de_sortie, nom_fichier)
        
        print(f"\n--- Traitement du bulletin n°{numero_bulletin} ---")
        print(f"URL : {lien}")

        succes = extraire_page_connectee(lien, chemin_complet, vos_cookies)
        
        if succes:
            print(f"✅ Sauvegardé avec succès dans : '{chemin_complet}'")
        else:
            print(f"🔴 Échec de la sauvegarde pour le bulletin n°{numero_bulletin}.")
        
        # Petite pause pour ne pas surcharger le serveur
        time.sleep(1) 

    print("\n🎉🎉🎉 Processus terminé ! 🎉🎉🎉")