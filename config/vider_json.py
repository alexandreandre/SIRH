import json
import os
from pathlib import Path

def vider_objet(obj):
    """Retourne une version 'vide' de l'objet JSON donné."""
    if isinstance(obj, dict):
        return {k: vider_objet(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return []
    elif isinstance(obj, (int, float)):
        return 0
    elif isinstance(obj, str):
        return ""
    elif obj is None:
        return None
    else:
        return None  # fallback

def creer_version_vide(fichier_entree: str):
    # Charger le fichier JSON
    with open(fichier_entree, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Générer la version vide
    data_vide = vider_objet(data)

    # Créer le dossier config si besoin
    Path("config").mkdir(exist_ok=True)

    # Nom de sortie
    fichier_sortie = Path("config") / Path(fichier_entree).name

    # Sauvegarde
    with open(fichier_sortie, "w", encoding="utf-8") as f:
        json.dump(data_vide, f, indent=2, ensure_ascii=False)

    print(f"Fichier vide créé : {fichier_sortie}")

# Exemple d'utilisation
if __name__ == "__main__":
    creer_version_vide("config/taux_cotisations.json")
