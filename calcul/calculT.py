# scripts/calculT.py

import json

def calculer_parametre_T():
    """
    Calcule la valeur du paramètre T en se basant sur les fichiers de configuration.
    Cette méthode simule le calcul automatique d'un logiciel de paie.
    """
    try:
        with open('config/taux_cotisations.json', 'r', encoding='utf-8') as f:
            taux_cotisations = json.load(f)['TAUX_COTISATIONS']
        with open('config/parametres_entreprise.json', 'r', encoding='utf-8') as f:
            entreprise = json.load(f)['PARAMETRES_ENTREPRISE']
    except Exception as e:
        print(f"Erreur lors du chargement des fichiers pour le calcul de T : {e}")
        return None

    # Liste des clés des cotisations patronales incluses dans le calcul de T
    cles_incluses_dans_T = [
        "securite_sociale_maladie",
        "retraite_secu_plafond",
        "retraite_secu_deplafond",
        "allocations_familiales",
        "fnal",
        "csa",
        "retraite_comp_t1",
        "ceg_t1"
    ]

    valeur_T = 0
    
    print("\n--- Calcul du Paramètre T ---")
    
    # 1. Additionner les taux des cotisations listées
    for cle in cles_incluses_dans_T:
        taux_patronal = taux_cotisations[cle].get('patronal', 0)
        valeur_T += taux_patronal
        print(f"  + {taux_cotisations[cle]['libelle']:<45} : {taux_patronal:.4f}")

    # 2. Gérer le cas particulier de la cotisation Accidents du Travail (AT/MP)
    taux_at_reel = entreprise['conditions_cotisations'].get('taux_accident_travail', 0)
    # La loi plafonne la prise en compte du taux AT/MP dans le calcul de T (0.55% en 2024/début 2025)
    taux_at_pour_T = min(taux_at_reel, 0.0055) 
    
    valeur_T += taux_at_pour_T
    print(f"  + {'Cotisation Accidents du travail (part pour T)':<45} : {taux_at_pour_T:.4f} (Taux réel: {taux_at_reel})")
    
    valeur_T = round(valeur_T, 4)
    print(f"-------------------------------------------------------")
    print(f"VALEUR TOTALE DE T CALCULÉE : {valeur_T}")
    
    return valeur_T

# Permet de tester le script indépendamment
if __name__ == "__main__":
    calculer_parametre_T()