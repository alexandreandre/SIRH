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

def extraire_liens_des_cartes(url_page_principale, selecteur_css, cookies_session):
    """
    Se connecte à une page, trouve tous les liens correspondant à un sélecteur CSS
    et retourne une liste d'URL absolues.
    """
    print(f"🔎 Analyse de la page principale : {url_page_principale}")
    liens_trouves = []
    
    try:
        reponse = requests.get(url_page_principale, cookies=cookies_session)
        reponse.raise_for_status()
        
        soup = BeautifulSoup(reponse.text, 'html.parser')
        
        elements_liens = soup.select(selecteur_css)
        
        if not elements_liens:
            print("⚠️ Aucun lien trouvé. Le sélecteur ou la structure de la page a peut-être changé.")
            return []

        for element in elements_liens:
            href = element.get('href')
            if href:
                url_absolue = urljoin(url_page_principale, href)
                liens_trouves.append(url_absolue)
        
        print(f"✅ {len(liens_trouves)} liens de bulletins trouvés !")
        return liens_trouves

    except requests.exceptions.RequestException as e:
        print(f"❌ Erreur lors de l'accès à la page principale : {e}")
        return []

def extraire_page_connectee(url, chemin_fichier_sortie, cookies_session):
    """
    Extrait le HTML et le CSS d'une page et sauvegarde le résultat dans un fichier unique.
    """
    try:
        reponse = requests.get(url, cookies=cookies_session)
        reponse.raise_for_status()

        soup = BeautifulSoup(reponse.text, 'html.parser')

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
                except requests.exceptions.RequestException:
                    pass # Ignore les CSS qui ne peuvent pas être chargés

        with open(chemin_fichier_sortie, 'w', encoding='utf-8') as f:
            f.write(str(soup))
            
        return True

    except requests.exceptions.RequestException as e:
        print(f"   ❌ Erreur lors du téléchargement de la page : {e}")
        return False

# --- CONFIGURATION ---
if __name__ == '__main__':
    # 1. URL de la page qui liste TOUS les bulletins
    url_avec_les_cartes = "https://www.legisocial.fr/bulletin-paie-commente/"

    # 2. Le sélecteur CSS que nous avons identifié grâce à votre HTML.
    selecteur_pour_les_liens = "article.item h2 a"

    # 3. Nom du dossier où seront sauvegardés les fichiers.
    dossier_de_sortie = "Bulletins_Legisocial"

    # 4. Vos cookies de session. Assurez-vous qu'ils sont toujours valides !
    vos_cookies = {
        'PHPSESSID': 'o8h8d358jtlii0vn6vof0a2vvf' 
    }

    # --- EXÉCUTION DU SCRIPT ---
    
    # Étape 1 : Extraire la liste des liens
    liste_des_liens = extraire_liens_des_cartes(url_avec_les_cartes, selecteur_pour_les_liens, vos_cookies)
    
    # Étape 2 : Sauvegarder chaque page si des liens ont été trouvés
    if not liste_des_liens:
        print("\nProcessus arrêté car aucun lien n'a été trouvé.")
    else:
        creer_dossier_si_necessaire(dossier_de_sortie)
        print(f"\n🚀 Démarrage de la sauvegarde de {len(liste_des_liens)} page(s) dans '{dossier_de_sortie}'...")

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
            
            time.sleep(1)

        print("\n🎉🎉🎉 Processus complet terminé ! 🎉🎉🎉")