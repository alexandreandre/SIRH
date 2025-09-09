# VM.py

import requests
from bs4 import BeautifulSoup
import os
from urllib.parse import urljoin
import csv
import json
import pandas as pd

def download_file(url, folder, headers):
    """
    Télécharge un fichier depuis une URL et le sauvegarde dans le dossier spécifié.
    Retourne le chemin du fichier téléchargé en cas de succès, sinon None.
    """
    try:
        local_filename = os.path.basename(url.split('?')[0])
        path_to_save = os.path.join(folder, local_filename)
        
        print(f"Téléchargement de : {url}")
        # Utilise les en-têtes (headers) pour la requête de téléchargement aussi
        with requests.get(url, stream=True, headers=headers) as r:
            r.raise_for_status()
            with open(path_to_save, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
        print(f"-> Fichier brut sauvegardé sous : {path_to_save}")
        return path_to_save
    except requests.exceptions.RequestException as e:
        print(f"❌ Erreur lors du téléchargement de {url}: {e}\n")
        return None

def convert_csv_to_json(csv_path, json_path):
    """
    Convertit un fichier CSV (avec point-virgule comme délimiteur) en JSON.
    """
    print(f"Conversion de '{os.path.basename(csv_path)}' en JSON...")
    records = []
    try:
        with open(csv_path, mode='r', encoding='latin-1', newline='') as csv_file:
            csv_reader = csv.DictReader(csv_file, delimiter=';')
            for row in csv_reader:
                records.append(row)
        
        with open(json_path, 'w', encoding='utf-8') as json_file:
            json.dump(records, json_file, indent=4, ensure_ascii=False)
            
        print(f"✅ Succès ! Fichier JSON sauvegardé sous : {json_path}\n")
    except Exception as e:
        print(f"❌ Erreur lors de la conversion CSV -> JSON : {e}\n")

def convert_xlsx_to_json(xlsx_path, json_path):
    """
    Convertit un fichier XLSX en JSON en utilisant la bibliothèque pandas.
    """
    print(f"Conversion de '{os.path.basename(xlsx_path)}' en JSON...")
    try:
        df = pd.read_excel(xlsx_path)
        df.to_json(json_path, orient='records', indent=4, force_ascii=False)
        
        print(f"✅ Succès ! Fichier JSON sauvegardé sous : {json_path}\n")
    except Exception as e:
        print(f"❌ Erreur lors de la conversion XLSX -> JSON : {e}\n")

def main():
    """
    Fonction principale qui orchestre le téléchargement et la conversion des fichiers.
    """
    PAGE_URL = "https://fichierdirect.declaration.urssaf.fr/TablesReference.htm"
    DOWNLOAD_FOLDER = "fichiers_urssaf"
    CONFIG_FOLDER = "config"

    # En-tête pour simuler un navigateur web et éviter d'être bloqué
    HEADERS = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.0.0 Safari/537.36'
    }

    for folder in [DOWNLOAD_FOLDER, CONFIG_FOLDER]:
        if not os.path.exists(folder):
            os.makedirs(folder)
            print(f"Dossier '{folder}' créé.")

    print(f"\nScraping de la page : {PAGE_URL}")
    
    try:
        # AJOUT : On passe les HEADERS à la requête
        response = requests.get(PAGE_URL, headers=HEADERS)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        print(f"Impossible d'accéder à la page. Erreur : {e}")
        return

    soup = BeautifulSoup(response.text, 'html.parser')

    files_to_find = {
        'url_codcoms': 'Table des taux transport (.csv)',
        'url_vmrr': 'Table des taux du Versement Mobilité (.xlsx)'
    }

    for html_id, description in files_to_find.items():
        print(f"--- Recherche de '{description}' ---")
        link_tag = soup.find('a', id=html_id)
        
        if link_tag and link_tag.has_attr('href'):
            relative_path = link_tag['href']
            absolute_url = urljoin(PAGE_URL, relative_path)
            
            # 1. Téléchargement (on passe aussi les HEADERS ici)
            downloaded_file_path = download_file(absolute_url, DOWNLOAD_FOLDER, HEADERS)
            
            # 2. Conversion
            if downloaded_file_path:
                filename_without_ext = os.path.splitext(os.path.basename(downloaded_file_path))[0]
                json_output_path = os.path.join(CONFIG_FOLDER, f"{filename_without_ext}.json")
                
                if downloaded_file_path.lower().endswith('.csv'):
                    convert_csv_to_json(downloaded_file_path, json_output_path)
                elif downloaded_file_path.lower().endswith('.xlsx'):
                    convert_xlsx_to_json(downloaded_file_path, json_output_path)
        else:
            print(f"❌ Impossible de trouver le lien de téléchargement pour l'id '{html_id}'.\n")

if __name__ == "__main__":
    main()