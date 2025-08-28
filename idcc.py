import requests
import json
import time  # <--- Assurez-vous que cette ligne est bien présente !

# --- Configuration ---
# Remplacez par vos identifiants obtenus sur PISTE
CLIENT_ID = "13ff509c-9cc0-451c-85c0-5f34007c3ccf"
CLIENT_SECRET = "9e9e26ed-c705-446c-a6d9-894939b4be9c"

# Liste des IDCC que nous allons tester
IDCC_A_TESTER = [
    "1486",  # Bureaux d'études techniques (celui qui échoue)
    "2098",  # Personnel des prestataires de services
    "1516",  # Organismes de formation
    "1090",  # Services de l'automobile
    "0044"   # Industries chimiques
]

# URLs des points de terminaison de l'API PISTE
URL_TOKEN = "https://oauth.piste.gouv.fr/api/oauth/token"
URL_API_LEGIFRANCE = "https://api.piste.gouv.fr/dila/legifrance/lf-engine-app"

def obtenir_token():
    """
    Récupère un jeton d'accès auprès de l'API PISTE.
    """
    headers = {
        "Content-Type": "application/x-www-form-urlencoded"
    }
    data = {
        "grant_type": "client_credentials",
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "scope": "openid"
    }
    try:
        response = requests.post(URL_TOKEN, headers=headers, data=data)
        response.raise_for_status()
        return response.json().get("access_token")
    except requests.exceptions.RequestException as e:
        print(f"Erreur lors de l'obtention du token : {e}")
        return None

def rechercher_textes_kali(token, idcc):
    """
    Recherche les textes pour une convention collective donnée (version simplifiée).
    """
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    payload = {
        "recherche": {
            "fond": "KALI",
            "champs": [
                {
                    "typeChamp": "IDCC",
                    "criteres": [
                        {
                            "typeRecherche": "EXACTE",
                            "valeur": idcc
                        }
                    ]
                }
            ],
            "pageNumber": 1,
            "pageSize": 10,
            "sort": "CHRONO_DATE_PUBLI"
        }
    }

    try:
        response = requests.post(f"{URL_API_LEGIFRANCE}/search", headers=headers, data=json.dumps(payload))
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Erreur lors de la recherche pour l'IDCC {idcc} : {e}")
        if e.response is not None:
            print(f"Détail de l'erreur du serveur : {e.response.text}")
        return None

def main():
    """
    Fonction principale pour exécuter le script.
    """
    token = obtenir_token()
    if not token:
        return

    print("Token d'accès obtenu avec succès.\n")

    # On boucle sur chaque IDCC de notre liste de test
    for idcc_a_tester in IDCC_A_TESTER:
        print(f"--- Test avec l'IDCC : {idcc_a_tester} ---")
        resultats = rechercher_textes_kali(token, idcc_a_tester)

        if resultats and "results" in resultats:
            nombre_resultats = len(resultats["results"])
            print(f"✅ SUCCÈS : {nombre_resultats} texte(s) trouvé(s) pour l'IDCC {idcc_a_tester}.")
        else:
            print(f"❌ ÉCHEC pour l'IDCC {idcc_a_tester}.")
        
        # Petite pause pour ne pas surcharger l'API
        time.sleep(1)
        print("-" * 35 + "\n")


if __name__ == "__main__":
    main()