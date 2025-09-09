# moteur_paie/calcul_T.py

import sys
from .contexte import ContextePaie
from typing import Dict, Any

def calculer_parametre_T(contexte: ContextePaie) -> float:
    """
    Calcule la valeur du paramètre T en se basant sur le contexte de paie chargé.
    Cette méthode simule le calcul automatique d'un logiciel de paie.
    """
    # Liste des cotisations patronales incluses dans le calcul de T
    cles_incluses_dans_T = [
        "securite_sociale_maladie",
        "retraite_secu_plafond",
        "retraite_secu_deplafond",
        "allocations_familiales",
        "fnal",
        "csa",
        "assurance_chomage",
        "retraite_comp_t1",
        "ceg_t1"
    ]

    valeur_T = 0.0
    
    print("--- Calcul du Paramètre T ---", file=sys.stderr)
    
    # 1. Additionner les taux des cotisations listées
    for cle in cles_incluses_dans_T:
        coti_data = contexte.get_cotisation_by_id(cle)
        if not coti_data:
            print(f"AVERTISSEMENT: Cotisation '{cle}' non trouvée pour le calcul de T.", file=sys.stderr)
            continue

        taux_patronal_brut = coti_data.get('patronal')
        taux_a_ajouter = 0.0

        # Résoudre les taux qui dépendent du contexte
        if cle == 'fnal' and isinstance(taux_patronal_brut, dict):
            taux_a_ajouter = (taux_patronal_brut.get('taux_moins_50') if contexte.effectif < 50 
                            else taux_patronal_brut.get('taux_50_et_plus'))
        elif cle == 'allocations_familiales':
            # Pour le calcul de T, on prend toujours le taux plein
            taux_a_ajouter = coti_data.get('patronal_plein')
        elif isinstance(taux_patronal_brut, (int, float)):
             taux_a_ajouter = taux_patronal_brut
        
        taux_a_ajouter = taux_a_ajouter or 0.0
        valeur_T += taux_a_ajouter
        print(f"  + {coti_data.get('libelle', cle):<45} : {taux_a_ajouter:.4f}", file=sys.stderr)

    # 2. Gérer le cas particulier de la cotisation Accidents du Travail (AT/MP)
    taux_at_reel = contexte.entreprise.get('parametres_paie', {}).get('taux_specifiques', {}).get('taux_at_mp', 0.0)
    
    # La loi plafonne la prise en compte du taux AT/MP dans le calcul de T
    TAUX_AT_POUR_T_MAX = 0.0046 # Valeur de référence pour 2025
    taux_at_pour_T = min(taux_at_reel, TAUX_AT_POUR_T_MAX) 
    
    valeur_T += taux_at_pour_T
    print(f"  + {'Cotisation Accidents du travail (part pour T)':<45} : {taux_at_pour_T:.4f} (Taux réel: {taux_at_reel})", file=sys.stderr)
    
    valeur_T = round(valeur_T, 4)
    print(f"-------------------------------------------------------", file=sys.stderr)
    print(f"VALEUR TOTALE DE T CALCULÉE : {valeur_T}", file=sys.stderr)
    
    return valeur_T