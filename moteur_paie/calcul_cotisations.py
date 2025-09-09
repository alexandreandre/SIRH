# moteur_paie/calcul_cotisations.py

import sys
from .contexte import ContextePaie
from typing import Dict, Any, List, Tuple

def _calculer_assiettes(contexte: ContextePaie, salaire_brut: float, remuneration_heures_supp: float) -> Dict[str, float]:
    """Prépare toutes les bases de calcul (assiettes) nécessaires pour les cotisations."""
    pss = contexte.baremes.get('pss', {}).get('mensuel', 0.0)
    
    # Assiettes conditionnelles
    assiette_tranche_2 = 0.0
    assiette_cet = 0.0
    if salaire_brut > pss:
        assiette_tranche_2 = max(0, min(salaire_brut, 8 * pss) - pss)
        assiette_cet = min(salaire_brut, 8 * pss)
    
    # Parts patronales pour la base CSG
    mutuelle_spec = contexte.contrat.get('specificites_paie', {}).get('mutuelle', {})
    part_patronale_frais_sante = mutuelle_spec.get('montant_patronal', 0.0)

    id_prevoyance_applicable = 'prevoyance_cadre' if contexte.statut_salarie == 'Cadre' else 'prevoyance_non_cadre'
    cotisation_prevoyance = contexte.get_cotisation_by_id(id_prevoyance_applicable)
    part_patronale_prevoyance = 0.0
    if cotisation_prevoyance and cotisation_prevoyance.get('patronal'):
        taux_prevoyance = cotisation_prevoyance['patronal']
        assiette_prevoyance = min(salaire_brut, pss)
        part_patronale_prevoyance = assiette_prevoyance * taux_prevoyance
        
    # --- CALCUL ASSIETTE CSG CORRIGÉ ---
    # Formule: (Brut hors HS * 98.25%) + (Part Pat. Prév/Santé)
    # Les HS sont soumises à 100% à la CSG/CRDS (depuis 2019)
    salaire_brut_hors_hs = salaire_brut - remuneration_heures_supp
    
    base_csg_normale = (salaire_brut_hors_hs * 0.9825) + part_patronale_prevoyance + part_patronale_frais_sante
    base_csg_hs = remuneration_heures_supp*0.9825

    return {
        "brut": salaire_brut, "plafond_ss": pss,
        "brut_plafonne": min(salaire_brut, pss),
        "tranche_2": round(assiette_tranche_2, 2),
        "assiette_cet": round(assiette_cet, 2),
        "csg_crds_base_normale": round(base_csg_normale, 2),
        "csg_crds_base_hs": round(base_csg_hs, 2)
    }

def _calculer_une_ligne(libelle: str, assiette: float, taux_salarial: float, taux_patronal: float) -> Dict[str, Any] | None:
    if assiette <= 0 and not (taux_salarial is None and taux_patronal is None): return None
    montant_salarial = round(assiette * (taux_salarial or 0.0), 2)
    montant_patronal = round(assiette * (taux_patronal or 0.0), 2)
    if montant_salarial == 0 and montant_patronal == 0: return None
    return {
        "libelle": libelle, "base": assiette, "taux_salarial": taux_salarial, 
        "montant_salarial": montant_salarial, "taux_patronal": taux_patronal, "montant_patronal": montant_patronal
    }

def calculer_cotisations(
    contexte: ContextePaie, 
    salaire_brut: float, 
    remuneration_heures_supp: float = 0.0,
    total_heures_supp: float = 0.0 # <-- CORRECTION
) -> Tuple[List[Dict[str, Any]], float]:
    """
    Calcule toutes les cotisations sociales, salariales et patronales.
    """
    print("INFO: Démarrage du calcul des cotisations...", file=sys.stderr)
    
    assiettes = _calculer_assiettes(contexte, salaire_brut, remuneration_heures_supp)
    root_key = next((k for k, v in contexte.baremes['cotisations'].items() if isinstance(v, list)), "cotisations")
    liste_cotisations_brutes = contexte.baremes['cotisations'].get(root_key, [])
    bulletin_cotisations = []
    
    for coti_data in liste_cotisations_brutes:
        coti_id = coti_data.get('id')

        # Filtres d'application
        if (coti_id == 'prevoyance_cadre' or coti_id == 'apec') and contexte.statut_salarie != 'Cadre': continue
        if coti_id == 'prevoyance_non_cadre' and contexte.statut_salarie != 'Non-Cadre': continue
        if coti_id == 'mutuelle': continue # Géré manuellement plus bas

        libelle = coti_data.get('libelle', '')
        base_id = coti_data.get('base', 'brut')
        assiette = assiettes.get(base_id, assiettes['brut_plafonne'] if base_id == 'plafond_ss' else assiettes['brut'])
        
        taux_salarial = coti_data.get('salarial')
        taux_patronal_brut = coti_data.get('patronal')
        taux_patronal_final = taux_patronal_brut

        if isinstance(taux_patronal_brut, dict):
            if coti_id == 'fnal':
                taux_patronal_final = (taux_patronal_brut.get('taux_moins_50') if contexte.effectif < 50 else taux_patronal_brut.get('taux_50_et_plus'))
            elif coti_id == 'CFP':
                taux_patronal_final = (taux_patronal_brut.get('taux_moins_11') if contexte.effectif < 11 else taux_patronal_brut.get('taux_11_et_plus'))
            elif coti_id in ['taxe_apprentissage', 'taxe_apprentissage_solde']:
                taux_patronal_final = (taux_patronal_brut.get('taux_alsace_moselle') if contexte.is_alsace_moselle else taux_patronal_brut.get('taux_metropole'))
            else:
                taux_patronal_final = 0.0
        
        smic_mensuel = contexte.baremes.get('smic', {}).get('cas_general', 0.0) * 35 * 52 / 12
        if coti_id == 'allocations_familiales':
            taux_patronal_final = (coti_data.get('patronal_reduit') if salaire_brut <= 3.5 * smic_mensuel else coti_data.get('patronal_plein'))
        
        elif coti_id == 'securite_sociale_maladie':
            taux_patronal_final = (coti_data.get('patronal_reduit') if salaire_brut <= 2.5 * smic_mensuel else coti_data.get('patronal_plein'))
            if contexte.is_alsace_moselle:
                taux_salarial = coti_data.get('salarial_Alsace_Moselle', 0.0)
        
        elif coti_id == 'at_mp':
            taux_patronal_final = contexte.entreprise.get('parametres_paie', {}).get('taux_specifiques', {}).get('taux_at_mp', 0.0) / 100.0

        if coti_id == 'csg' and isinstance(taux_salarial, dict):
             taux_csg_deductible = taux_salarial.get('deductible', 0.0)
             taux_csg_non_deductible = taux_salarial.get('non_deductible', 0.0)
             taux_csg_total = taux_csg_deductible + taux_csg_non_deductible
             
             for ligne in [
                 _calculer_une_ligne("CSG déductible", assiettes['csg_crds_base_normale'], taux_csg_deductible, None),
                 _calculer_une_ligne("CSG/CRDS non déductible", assiettes['csg_crds_base_normale'], taux_csg_non_deductible, None),
                 _calculer_une_ligne("CSG/CRDS sur HS non déductible", assiettes['csg_crds_base_hs'], taux_csg_total, None)
             ]:
                 if ligne: bulletin_cotisations.append(ligne)
             continue

        if isinstance(taux_patronal_final, str):
            taux_patronal_final = 0.0

        ligne_calculee = _calculer_une_ligne(libelle, assiette, taux_salarial, taux_patronal_final)
        
        if ligne_calculee:
            bulletin_cotisations.append(ligne_calculee)
            
    # Ajout manuel des cotisations forfaitaires (mutuelle, etc.)
    mutuelle_spec = contexte.contrat.get('specificites_paie', {}).get('mutuelle', {})
    if mutuelle_spec.get('adhesion'):
        bulletin_cotisations.append({
            "libelle": "Mutuelle Frais de Santé", "base": None, "taux_salarial": None, 
            "montant_salarial": mutuelle_spec.get('montant_salarial', 0.0), "taux_patronal": None, 
            "montant_patronal": mutuelle_spec.get('montant_patronal', 0.0)
        })

    # Ajout de la réduction salariale sur les heures supplémentaires
    if remuneration_heures_supp > 0:
        taux_reduction = contexte.baremes.get('heures_supp', {}).get('reduction_salariale', {}).get('taux_reduction', {}).get('plafond_legal', 0.0)
        montant_reduction = round(-remuneration_heures_supp * taux_reduction, 2)
        bulletin_cotisations.append({
            "libelle": "Réduction de cotisations sur heures sup.", 
            "base": remuneration_heures_supp, "taux_salarial": -taux_reduction, 
            "montant_salarial": montant_reduction, "taux_patronal": None, "montant_patronal": 0.0
            })

    # --- NOUVEAU BLOC DE CALCUL ---
    # Ajout de la déduction forfaitaire patronale sur les heures supplémentaires
    regles_deduction = contexte.baremes.get('heures_supp', {}).get('deduction_patronale', {})
    if total_heures_supp > 0 and regles_deduction:
        montant_par_heure = 0.0
        for palier in regles_deduction.get('montants_forfaitaires', []):
            # On vérifie si l'effectif est dans la tranche du palier (<20 salariés est max 19)
            if palier.get('effectif_min', 0) <= contexte.effectif <= palier.get('effectif_max', 19):
                montant_par_heure = palier.get('montant_par_heure_sup_eur', 0.0)
                break
        
        if montant_par_heure > 0:
            montant_deduction = round(-total_heures_supp * montant_par_heure, 2)
            bulletin_cotisations.append({
                "libelle": "Déduction forfaitaire heures suppl. pat.",
                "base": total_heures_supp,
                "taux_salarial": None,
                "montant_salarial": 0.0,
                "taux_patronal": None, 
                "montant_patronal": montant_deduction
            })
    # --- FIN DU NOUVEAU BLOC ---

    total_cotisations_salariales = sum(ligne.get('montant_salarial', 0.0) or 0.0 for ligne in bulletin_cotisations)
    print("INFO: Calcul des cotisations terminé.", file=sys.stderr)
    return bulletin_cotisations, round(total_cotisations_salariales, 2)