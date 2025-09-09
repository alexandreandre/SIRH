# moteur_paie/calcul_reduction_generale.py

import sys
from .contexte import ContextePaie
from .calculT import calculer_parametre_T
from typing import Dict, Any, List

def calculer_reduction_generale(
    contexte: ContextePaie, 
    salaire_brut: float, 
    calendrier_saisie: List[Dict[str, Any]], # <-- SIGNATURE MODIFIÉE
) -> Dict[str, Any] | None:
    """
    Calcule le montant de la Réduction Générale des Cotisations Patronales
    en appliquant la méthode de la régularisation progressive annuelle.
    """
    print("INFO: Démarrage du calcul de la Réduction Générale (avec régularisation)...", file=sys.stderr)

    smic_horaire = contexte.baremes.get('smic', {}).get('cas_general', 0.0)
    if smic_horaire == 0.0:
        return None

    cumuls_precedents = contexte.cumuls_annee_precedente
    
    # --- BLOC DE CALCUL DES HEURES RÉÉCRIT POUR LE CALENDRIER ---
    # 1. Heures contractuelles du mois (incluant HS structurelles)
    duree_contrat_hebdo = contexte.duree_hebdo_contrat
    heures_contractuelles_mois = round((duree_contrat_hebdo * 52) / 12, 2)

    # 2. Heures supplémentaires conjoncturelles (au-delà du contrat)
    heures_travaillees_reelles = sum(j.get('heures', 0) for j in calendrier_saisie if j.get('type') == 'travail')
    jours_de_conges = sum(1 for j in calendrier_saisie if j.get('type') == 'conges_payes')
    heures_dues_hors_conges = heures_contractuelles_mois - (jours_de_conges * (duree_contrat_hebdo / 5))
    heures_sup_conjoncturelles_mois = max(0, heures_travaillees_reelles - heures_dues_hors_conges)

    # 3. Total des heures pour le SMIC = Heures du contrat + HS en plus
    # (Le SMIC est maintenu pendant les congés, donc on se base sur les heures contractuelles totales)
    total_heures_mois = heures_contractuelles_mois + heures_sup_conjoncturelles_mois
    # --- FIN DU BLOC RÉÉCRIT ---
    
    salaire_brut_cumule = cumuls_precedents.get('brut_total', 0.0) + salaire_brut
    smic_annuel_cumule = cumuls_precedents.get('smic_calcule', 0.0) + (smic_horaire * total_heures_mois)
    
    seuil_eligibilite_cumule = 1.6 * smic_annuel_cumule
    
    print(f"DEBUG [Réduction Cumulée]: Salaire brut cumulé = {salaire_brut_cumule:.2f} €", file=sys.stderr)
    print(f"DEBUG [Réduction Cumulée]: SMIC de référence cumulé = {smic_annuel_cumule:.2f} €", file=sys.stderr)
    print(f"DEBUG [Réduction Cumulée]: Seuil d'éligibilité (1.6 * SMIC) = {seuil_eligibilite_cumule:.2f} €", file=sys.stderr)

    if salaire_brut_cumule >= seuil_eligibilite_cumule:
        print("INFO: Cumul annuel > 1.6 SMIC. Le droit à la réduction pour l'année est épuisé.", file=sys.stderr)
        reduction_deja_versee = abs(cumuls_precedents.get('reduction_generale_patronale', 0.0))
        if reduction_deja_versee > 0:
            return {
                "libelle": "Régularisation Réduction Générale", "base": salaire_brut,
                "taux_salarial": None, "montant_salarial": 0.0,
                "taux_patronal": None, "montant_patronal": reduction_deja_versee
                }
        return None

    parametre_T = calculer_parametre_T(contexte)
    if not parametre_T:
        return None

    # On s'assure de ne pas diviser par zéro si le salaire brut cumulé est nul
    if salaire_brut_cumule == 0:
        return None

    coefficient_C_annuel = (parametre_T / 0.6) * ( (1.6 * smic_annuel_cumule / salaire_brut_cumule) - 1 )
    coefficient_C_annuel = max(0, coefficient_C_annuel)

    droit_total_reduction = salaire_brut_cumule * coefficient_C_annuel
    
    reduction_deja_appliquee = abs(cumuls_precedents.get('reduction_generale_patronale', 0.0))
    
    montant_reduction_mois = droit_total_reduction - reduction_deja_appliquee
    montant_final = -round(montant_reduction_mois, 2)

    print(f"INFO: Réduction Générale calculée (régularisée) : {montant_final} €", file=sys.stderr)

    return {
        "libelle": "Réduction générale de cotisations patronales",
        "base": salaire_brut,
        "taux_salarial": None,
        "montant_salarial": 0.0,
        "taux_patronal": round(coefficient_C_annuel, 6),
        "montant_patronal": montant_final
    }