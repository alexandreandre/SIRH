# moteur_paie/calcul_conges.py

import sys
from .contexte import ContextePaie
from typing import Dict, Any

def calculer_indemnite_conges(
    contexte: ContextePaie,
    nombre_jours_conges: int,
    salaire_horaire_base: float
) -> Dict[str, Any]:
    """
    Calcule l'indemnité de congés payés en comparant les deux méthodes
    et en retournant la plus avantageuse pour le salarié, en tenant compte des HS structurelles.
    """
    print("INFO: Démarrage du calcul de l'indemnité de congés payés...", file=sys.stderr)

    # --- Calcul des heures et montants pour le maintien de salaire ---
    heures_normales_par_jour = 35 / 5
    heures_supp_structurelles_par_jour = (contexte.duree_hebdo_contrat - 35) / 5
    
    total_heures_normales_absence = nombre_jours_conges * heures_normales_par_jour
    total_heures_supp_absence = nombre_jours_conges * heures_supp_structurelles_par_jour
    total_heures_absence_global = total_heures_normales_absence + total_heures_supp_absence
    
    majoration_hs = contexte.baremes.get('heures_supp', {}).get('regles_calcul_communes', {}).get('taux_majoration_par_defaut', {}).get('heures_supplementaires', [{}])[0].get('taux', 0.25)
    salaire_horaire_majore = salaire_horaire_base * (1 + majoration_hs)

    # Calcul des montants sans arrondi initial
    indemnite_maintien_part_normale_raw = total_heures_normales_absence * salaire_horaire_base
    indemnite_maintien_part_hs_raw = total_heures_supp_absence * salaire_horaire_majore
    indemnite_maintien_total_raw = indemnite_maintien_part_normale_raw + indemnite_maintien_part_hs_raw

    # Correction de l'arrondi
    indemnite_maintien_total = round(indemnite_maintien_total_raw, 2)
    indemnite_maintien_part_hs = round(indemnite_maintien_part_hs_raw, 2)
    indemnite_maintien_part_normale = indemnite_maintien_total - indemnite_maintien_part_hs

    # --- Méthode 2 : Règle du 1/10ème ---
    brut_reference_n_1 = contexte.cumuls.get('cumuls', {}).get('brut_reference_n_1', 0.0)
    valeur_un_jour_conge_10eme = (brut_reference_n_1 * 0.10) / 30 if brut_reference_n_1 > 0 else 0
    indemnite_10eme = round(nombre_jours_conges * valeur_un_jour_conge_10eme, 2)
    
    # --- Arbitrage (inchangé) ---
    indemnite_finale = max(indemnite_maintien_total, indemnite_10eme)
    methode_retenue = "1/10ème" if indemnite_finale > indemnite_maintien_total else "Maintien"
    
    print("\n--- Arbitrage Indemnité Congés Payés ---", file=sys.stderr)
    print(f"\tMéthode 'Maintien de salaire'  : {indemnite_maintien_total:10.2f} €", file=sys.stderr)
    print(f"\tMéthode 'Règle du 1/10ème'     : {indemnite_10eme:10.2f} €", file=sys.stderr)
    print(f"\t--------------------------------------------", file=sys.stderr)
    print(f"\tMontant retenu (plus avantageux) : {indemnite_finale:10.2f} € (Méthode: {methode_retenue})", file=sys.stderr)
    print("----------------------------------------\n", file=sys.stderr)
    
    # --- Le dictionnaire de retour est enrichi avec le détail des heures ---
    return {
        "montant_retenue": indemnite_maintien_total,
        "montant_indemnite": indemnite_finale,
        "indemnite_maintien_base": indemnite_maintien_part_normale,
        "indemnite_maintien_hs": indemnite_maintien_part_hs,
        "nombre_jours": nombre_jours_conges,
        "methode_retenue": methode_retenue,
        # NOUVEAU: On ajoute le détail des heures pour l'affichage
        "total_heures_absence": total_heures_absence_global,
        "heures_base": total_heures_normales_absence,
        "heures_hs": total_heures_supp_absence
    }