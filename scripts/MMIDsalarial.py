# scripts/MMIDsalarial.py

import json
import re
import requests
from bs4 import BeautifulSoup

FICHIER_CONTRAT = 'config/parametres_contrat.json'
FICHIER_TAUX = 'config/taux_cotisations.json'
URL_URSSAF = "https://www.urssaf.fr/accueil/outils-documentation/taux-baremes/taux-cotisations-secteur-prive.html"

def get_taux_alsace_moselle() -> float | None:
    """
    Scrape le site de l'URSSAF pour trouver le taux de la cotisation salariale
    spécifique à l'Alsace-Moselle avec une méthode de ciblage robuste.
    """
    try:
        print(f" scraping de l'URL : {URL_URSSAF}...")
        r = requests.get(URL_URSSAF, timeout=20, headers={
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
        })
        r.raise_for_status()

        soup = BeautifulSoup(r.text, "html.parser")
        
        # --- LOGIQUE DE CIBLAGE AMÉLIORÉE ---
        articles = soup.find_all('article')
        salarie_section_text = ""
        for article in articles:
            h2 = article.find('h2', class_='h4-like')
            if h2 and 'taux de cotisations salarié' in h2.get_text(strip=True).lower():
                salarie_section_text = article.get_text(" ", strip=True)
                break

        if not salarie_section_text:
            raise ValueError("Section 'Taux de cotisations salarié' introuvable.")
        
        motif = r"Cotisation salariale maladie supplémentaire.*?Moselle\s*([0-9,]+)\s*%"
        m = re.search(motif, salarie_section_text, flags=re.IGNORECASE)
        
        if not m:
            raise ValueError("Motif du taux Alsace-Moselle introuvable sur la page.")
        
        taux_str = m.group(1).replace(",", ".")
        taux = round(float(taux_str) / 100.0, 5) 
        
        print(f" Taux Alsace-Moselle trouvé : {taux*100:.2f}%")
        return taux
        
    except Exception as e:
        print(f"ERREUR : Le scraping du taux Alsace-Moselle a échoué. Raison : {e}")
        return None

def ajuster_taux_salarial_maladie():
    """
    Lit le paramètre isAlsaceMoselle, scrape le taux si nécessaire, et met à jour
    le fichier de cotisations.
    """
    try:
        with open(FICHIER_CONTRAT, 'r', encoding='utf-8') as f:
            config_contrat = json.load(f)
        
        # --- LOGIQUE CORRIGÉE ICI ---
        # On lit la clé depuis la sous-section "poste"
        is_alsace_moselle = config_contrat['PARAMETRES_CONTRAT']['poste'].get('isAlsaceMoselle', False)

        if is_alsace_moselle:
            print(f"Régime Alsace-Moselle détecté dans '{FICHIER_CONTRAT}'. Tentative de scraping...")
            taux_correct = get_taux_alsace_moselle()
            if taux_correct is None:
                print("Arrêt du script car le taux n'a pas pu être récupéré.")
                return 
        else:
            print(f"Régime général détecté dans '{FICHIER_CONTRAT}'.")
            taux_correct = 0

        with open(FICHIER_TAUX, 'r', encoding='utf-8') as f:
            config_taux = json.load(f)

        cotisation_maladie = config_taux['TAUX_COTISATIONS']['securite_sociale_maladie']
        taux_actuel = cotisation_maladie['salarial']
        
        if taux_actuel == taux_correct:
            print(f"Le taux salarial maladie dans '{FICHIER_TAUX}' est déjà correct ({taux_correct}). Aucune modification nécessaire.")
            return

        print(f"Mise à jour du taux salarial maladie : {taux_actuel} -> {taux_correct}")
        cotisation_maladie['salarial'] = taux_correct

        with open(FICHIER_TAUX, 'w', encoding='utf-8') as f:
            json.dump(config_taux, f, indent=2, ensure_ascii=False)
            
        print(f"✅ Le fichier '{FICHIER_TAUX}' a été mis à jour avec succès.")

    except FileNotFoundError as e:
        print(f"ERREUR : Le fichier '{e.filename}' est introuvable.")
    except KeyError as e:
        print(f"ERREUR : La structure d'un fichier JSON est incorrecte. La clé {e} est manquante.")
    except Exception as e:
        print(f"ERREUR : Une erreur inattendue est survenue : {e}")

if __name__ == "__main__":
    ajuster_taux_salarial_maladie()