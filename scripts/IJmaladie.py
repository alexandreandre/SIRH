# scripts/IJmaladie.py

# 

import json
import re
import requests
import time
from bs4 import BeautifulSoup

FICHIER_BAREMES = 'config/baremes.json'
URL_SERVICE_PUBLIC = "https://www.service-public.fr/particuliers/vosdroits/F3053"

# --- FONCTIONS UTILITAIRES ---
def make_robust_request(url, retries=3, delay=5):
    """Tente de se connecter à une URL plusieurs fois en cas d'échec."""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Accept-Language': 'fr-FR,fr;q=0.9',
    }
    for i in range(retries):
        try:
            print(f"Tentative de connexion n°{i + 1}/{retries}...")
            response = requests.get(url, headers=headers, timeout=20)
            response.raise_for_status()
            return response
        except requests.exceptions.RequestException as e:
            print(f"Échec de la tentative n°{i + 1}: {e}")
            if i < retries - 1:
                print(f"Nouvelle tentative dans {delay} secondes...")
                time.sleep(delay)
    return None

def parse_valeur_numerique(text):
    """Nettoie et convertit un texte en nombre (float)."""
    if not text: return 0.0
    cleaned = text.replace('€', '').replace('\xa0', '').replace('\u202f', '').replace(' ', '').replace(',', '.')
    match = re.search(r"([0-9]+\.?[0-9]*)", cleaned)
    return float(match.group(1)) if match else 0.0

# --- FONCTION DE SCRAPING DÉDIÉE ---

def get_plafond_ij() -> float | None:
    """
    Scrape le site service-public.fr pour trouver le montant maximum
    des indemnités journalières maladie.
    """
    try:
        response = make_robust_request(URL_SERVICE_PUBLIC)
        if not response:
            raise ConnectionError("Impossible de récupérer la page web après plusieurs tentatives.")
            
        soup = BeautifulSoup(response.text, "html.parser")
        
        # Ciblage précis de la section "Montant maximum"
        header = soup.find('h4', string=re.compile("Montant maximum"))
        if not header:
            raise ValueError("Section 'Montant maximum' introuvable sur la page.")
        
        # Le paragraphe contenant la valeur est juste après le titre
        p_valeur = header.find_next_sibling('p')
        if not p_valeur:
            raise ValueError("Paragraphe de valeur manquant après le titre 'Montant maximum'.")
            
        span_valeur = p_valeur.find('span', class_='sp-prix')
        if not span_valeur:
            raise ValueError("Span de prix manquant dans le paragraphe de valeur.")
        
        plafond = parse_valeur_numerique(span_valeur.get_text())
        print(f"  - Plafond de l'Indemnité Journalière trouvé : {plafond} €")
        return plafond

    except Exception as e:
        print(f"ERREUR : Le scraping a échoué. Raison : {e}")
        return None

def update_config_file(nouveau_plafond: float):
    """
    Met à jour le fichier baremes.json avec la nouvelle valeur.
    """
    try:
        with open(FICHIER_BAREMES, 'r', encoding='utf-8') as f:
            config = json.load(f)
        
        # Assurer que la structure existe
        config.setdefault('SECURITE_SOCIALE_2025', {}).setdefault('indemnites_journalieres_maladie', {})
        
        ij_config = config['SECURITE_SOCIALE_2025']['indemnites_journalieres_maladie']
        
        print("\nMise à jour du fichier de configuration...")
        ij_config['plafond_ij_base'] = nouveau_plafond
        
        with open(FICHIER_BAREMES, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
            
        print(f"✅ Le fichier '{FICHIER_BAREMES}' a été mis à jour avec succès.")
        
    except Exception as e:
        print(f"\nERREUR : Une erreur est survenue lors de la mise à jour : {e}")


if __name__ == "__main__":
    valeur = get_plafond_ij()
    
    if valeur is not None:
        update_config_file(valeur)