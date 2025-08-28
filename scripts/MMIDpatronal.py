# scripts/MMIDpatronal.py

import json
import re
import requests
from bs4 import BeautifulSoup

# Définir les chemins des fichiers
FICHIER_ENTREPRISE = 'config/parametres_entreprise.json'
FICHIER_TAUX = 'config/taux_cotisations.json'
URL_URSSAF = "https://www.urssaf.fr/accueil/outils-documentation/taux-baremes/taux-cotisations-secteur-prive.html"

def get_taux_maladie_patronal(is_taux_reduit: bool) -> float | None:
    """
    Scrape le site de l'URSSAF pour trouver le taux d'Assurance Maladie patronal
    (réduit ou plein) en fonction du booléen fourni.
    """
    try:
        print(f" scraping de l'URL : {URL_URSSAF}...")
        r = requests.get(URL_URSSAF, timeout=20, headers={
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
        })
        r.raise_for_status()

        soup = BeautifulSoup(r.text, "html.parser")
        
        # Cibler la section "employeur"
        articles = soup.find_all('article')
        employeur_section = None
        for article in articles:
            h2 = article.find('h2', class_='h4-like')
            if h2 and 'taux de cotisations employeur' in h2.get_text(strip=True).lower():
                employeur_section = article
                break

        if not employeur_section:
            raise ValueError("Section 'Taux de cotisations employeur' introuvable.")

        # Déterminer quel motif de texte chercher
        if is_taux_reduit:
            motif_recherche = r"Taux réduit à\s*([0-9,]+)\s*%"
            type_taux_log = "réduit"
        else:
            motif_recherche = r"Taux plein à\s*([0-9,]+)\s*%"
            type_taux_log = "plein"
            
        print(f"Recherche du taux d'assurance maladie : '{type_taux_log}'")

        # Parcourir les lignes du tableau pour trouver la bonne
        table_rows = employeur_section.find_all('tr', class_='table_custom__tbody')
        for row in table_rows:
            header_cell = row.find('th')
            # Si la ligne est celle de l'Assurance maladie...
            if header_cell and 'Assurance maladie' in header_cell.get_text(strip=True):
                value_cell = row.find('td')
                if not value_cell:
                    raise ValueError("Ligne 'Assurance maladie' trouvée, mais cellule de valeur manquante.")
                
                # ...appliquer le bon regex sur le contenu de la cellule de valeur
                m = re.search(motif_recherche, value_cell.get_text(strip=True), flags=re.IGNORECASE)
                if not m:
                    continue # Ce n'est pas le bon taux (plein/réduit), on continue

                taux_str = m.group(1).replace(",", ".")
                taux = round(float(taux_str) / 100.0, 5)
                
                print(f" Taux trouvé : {taux*100:.2f}%")
                return taux
        
        raise ValueError(f"Motif pour le taux '{type_taux_log}' de l'assurance maladie introuvable.")
        
    except Exception as e:
        print(f"ERREUR : Le scraping a échoué. Raison : {e}")
        return None

def update_config_file(nouveau_taux: float):
    """
    Lit le fichier JSON des taux et met à jour le taux patronal de l'assurance maladie.
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
        
    except FileNotFoundError:
        print(f"ERREUR : Le fichier '{FICHIER_TAUX}' est introuvable.")
    except KeyError as e:
        print(f"ERREUR : La structure du fichier '{FICHIER_TAUX}' est incorrecte. La clé {e} est manquante.")
    except Exception as e:
        print(f"ERREUR : Une erreur est survenue lors de la mise à jour : {e}")


if __name__ == "__main__":
    try:
        with open(FICHIER_ENTREPRISE, 'r', encoding='utf-8') as f:
            config_entreprise = json.load(f)
        
        # Détermine si on doit appliquer le taux réduit en lisant le paramètre de l'entreprise
        conditions = config_entreprise['PARAMETRES_ENTREPRISE']['conditions_cotisations']
        appliquer_taux_reduit = conditions.get('remuneration_annuelle_brute_inferieure_3.5_smic', False)

        taux = get_taux_maladie_patronal(is_taux_reduit=appliquer_taux_reduit)
    
        if taux is not None:
            update_config_file(taux)

    except FileNotFoundError:
        print(f"ERREUR : Le fichier '{FICHIER_ENTREPRISE}' est introuvable.")
    except KeyError as e:
        print(f"ERREUR : La structure du fichier '{FICHIER_ENTREPRISE}' est incorrecte ou une clé est manquante : {e}")