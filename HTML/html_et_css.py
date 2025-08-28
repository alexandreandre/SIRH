import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin

def extraire_page_connectee(url, nom_fichier_sortie, cookies_session):
    """
    Extrait le HTML et le CSS d'une page web nécessitant une connexion,
    en utilisant un cookie de session, et sauvegarde le tout dans un unique fichier HTML.

    Args:
        url (str): L'URL de la page web à traiter.
        nom_fichier_sortie (str): Le nom du fichier HTML de sortie.
        cookies_session (dict): Un dictionnaire contenant les cookies de session.
    """
    try:
        # La requête inclut maintenant votre cookie pour être authentifié
        reponse = requests.get(url, cookies=cookies_session)
        reponse.raise_for_status()  # Lève une exception pour les codes d'erreur HTTP

        print("✅ Accès à la page en mode connecté réussi !")

        soup = BeautifulSoup(reponse.text, 'html.parser')

        # Trouver et intégrer les feuilles de style externes
        print("🔎 Recherche des fichiers CSS...")
        for lien in soup.find_all('link', rel='stylesheet'):
            href = lien.get('href')
            if href:
                # Construit une URL absolue pour le fichier CSS
                url_css = urljoin(url, href)
                try:
                    # On réutilise les cookies de session pour télécharger le CSS
                    # au cas où il serait aussi protégé.
                    css_reponse = requests.get(url_css, cookies=cookies_session)
                    css_reponse.raise_for_status()
                    
                    # Remplacer le lien <link> par une balise <style> avec le contenu CSS
                    style_tag = soup.new_tag('style')
                    style_tag.string = css_reponse.text
                    lien.replace_with(style_tag)
                    print(f"   -> CSS intégré depuis : {url_css}")
                except requests.exceptions.RequestException as e:
                    print(f"   ⚠️ Impossible de télécharger le CSS depuis {url_css}: {e}")

        # Sauvegarder le HTML modifié
        with open(nom_fichier_sortie, 'w', encoding='utf-8') as f:
            f.write(str(soup))
            
        print(f"\n🎉 La page a été sauvegardée avec succès sous le nom de : {nom_fichier_sortie}")

    except requests.exceptions.RequestException as e:
        print(f"❌ Une erreur est survenue lors du téléchargement de la page : {e}")

# --- CONFIGURATION ---
if __name__ == '__main__':
    # 1. Mettez ici l'URL exacte de la page que vous voulez sauvegarder
    url_de_la_page = "https://www.legisocial.fr/modele-bulletin-paie/salarie-cadre-heures-supplementaires-structurelles-absence-maintenue-2025.html"

    # 2. Donnez un nom au fichier qui sera créé
    nom_du_fichier = "page_legisocial_connecte.html"

    # 3. C'est ici que vous mettez votre cookie de session
    # Le nom 'PHPSESSID' et sa valeur proviennent de votre analyse précédente.
    vos_cookies = {
        'PHPSESSID': 'o8h8d358jtlii0vn6vof0a2vvf'
    }

    # --- EXÉCUTION DU SCRIPT ---
    extraire_page_connectee(url_de_la_page, nom_du_fichier, vos_cookies)