# moteur_paie/calcul_net.py
import sys
from .contexte import ContextePaie
from typing import Dict, Any, List

def _get_safe_float(value: Any, default: float = 0.0) -> float:
    if value is None: return default
    return float(value)

# Dans le fichier moteur_paie/calcul_net.py

# Dans le fichier moteur_paie/calcul_net.py

def _calculer_net_imposable(
    contexte: ContextePaie, 
    salaire_brut: float, 
    total_cotisations_salariales: float, 
    lignes_cotisations: List[Dict[str, Any]],
    remuneration_heures_supp: float # <-- NOUVEAU: On passe le montant des HS
) -> float:
    
    # ... (les premières lignes pour calculer montant_csg_non_deductible et part_patronale_mutuelle ne changent pas)
    montant_csg_non_deductible = 0.0
    for ligne in lignes_cotisations:
        libelle = ligne.get('libelle', '').lower()
        if "csg/crds" in libelle and "non déductible" in libelle:
            montant_csg_non_deductible += _get_safe_float(ligne.get('montant_salarial'))
    
    mutuelle_spec = contexte.contrat.get('specificites_paie', {}).get('mutuelle', {})
    part_patronale_mutuelle = _get_safe_float(mutuelle_spec.get('montant_patronal', 0.0))
    
    salaire_brut_safe = _get_safe_float(salaire_brut)
    total_cotisations_safe = _get_safe_float(total_cotisations_salariales)
    
    # --- Formule standard du net imposable "brut" ---
    net_imposable_avant_defiscalisation = (salaire_brut_safe - total_cotisations_safe) + montant_csg_non_deductible + part_patronale_mutuelle
    
    # --- NOUVEAU : Application de la défiscalisation des HS ---
    # On soustrait le montant brut des HS (en s'assurant de ne pas dépasser le plafond annuel un jour)
    # Pour l'instant, on applique la défiscalisation sur tout le montant.
    net_imposable_final = net_imposable_avant_defiscalisation - remuneration_heures_supp

    # Le bloc de debug détaillé
    print("\n--- Calcul du Net Imposable ---", file=sys.stderr)
    print(f"\t  Net Social (Net à payer av. impôt) : {salaire_brut_safe - total_cotisations_safe:10.2f} €", file=sys.stderr)
    print(f"\t+ CSG/CRDS non déductible          : {montant_csg_non_deductible:10.2f} €", file=sys.stderr)
    print(f"\t+ Part Patronale Mutuelle          : {part_patronale_mutuelle:10.2f} €", file=sys.stderr)
    print(f"\t--------------------------------------------", file=sys.stderr)
    print(f"\t= Imposable avant défiscalisation  : {net_imposable_avant_defiscalisation:10.2f} €", file=sys.stderr)
    print(f"\t- Exonération Heures Supp.         : {remuneration_heures_supp:10.2f} €", file=sys.stderr)
    print(f"\t--------------------------------------------", file=sys.stderr)
    print(f"\t= NET IMPOSABLE                    : {round(net_imposable_final, 2):10.2f} €", file=sys.stderr)
    print("---------------------------------\n", file=sys.stderr)
    
    return round(net_imposable_final, 2)

def _calculer_prelevement_a_la_source(contexte: ContextePaie, net_imposable: float ) -> float:
    taux_pas = _get_safe_float(contexte.contrat.get('specificites_paie', {}).get('prelevement_a_la_source', {}).get('taux'))
    montant_pas = _get_safe_float(net_imposable) * (taux_pas / 100.0)
    return round(montant_pas, 2)



def _calculer_net_a_payer(net_social: float, montant_pas: float, contexte: ContextePaie, primes_non_soumises: List[Dict[str, Any]]) -> float:
    
    print("\n--- Calcul du Net À Payer ---", file=sys.stderr)
    print(f"\t  Net Social (base de départ)      : {net_social:10.2f} €", file=sys.stderr)
    print(f"\t- Impôt sur le revenu              : {montant_pas:10.2f} €", file=sys.stderr)
    
    net_apres_impot = _get_safe_float(net_social) - _get_safe_float(montant_pas)
    print(f"\t--------------------------------------------", file=sys.stderr)
    print(f"\t= Net après impôt                  : {net_apres_impot:10.2f} €", file=sys.stderr)

    # Initialisation du net à payer
    net_a_payer = net_apres_impot
    
    # Déduction des titres-restaurant
    tr_spec = contexte.contrat.get('specificites_paie', {}).get('titres_restaurant', {})
    if tr_spec.get('beneficie'):
        valeur_faciale = _get_safe_float(tr_spec.get('valeur_faciale'))
        part_patronale = _get_safe_float(tr_spec.get('part_patronale'))
        nombre_tr = _get_safe_float(tr_spec.get('nombre_par_mois'))
        part_salariale_tr = valeur_faciale - part_patronale
        deduction_tr = part_salariale_tr * nombre_tr
        
        print(f"\t- Déduction Titres-Restaurant      : {deduction_tr:10.2f} €", file=sys.stderr)
        net_a_payer -= deduction_tr
        
    # Ajout du remboursement transport
    transport_spec = contexte.contrat.get('specificites_paie', {}).get('transport', {})
    remboursement_transport = _get_safe_float(transport_spec.get('remboursement_abonnement_mensuel'))
    if remboursement_transport > 0:
        print(f"\t+ Remboursement Transport          : {remboursement_transport:10.2f} €", file=sys.stderr)
        net_a_payer += remboursement_transport
    
    # Ajout des primes non soumises
    montant_primes_non_soumises = 0.0
    for prime in primes_non_soumises:
        montant_prime = _get_safe_float(prime.get('montant'))
        montant_primes_non_soumises += montant_prime
        
    if montant_primes_non_soumises > 0:
        print(f"\t+ Primes non soumises              : {montant_primes_non_soumises:10.2f} €", file=sys.stderr)
        net_a_payer += montant_primes_non_soumises
    
    print(f"\t--------------------------------------------", file=sys.stderr)
    print(f"\t= NET À PAYER                      : {round(net_a_payer, 2):10.2f} €", file=sys.stderr)
    print("-----------------------------\n", file=sys.stderr)
    
    return round(net_a_payer, 2)


def calculer_net_et_impot(
    contexte: ContextePaie,
    salaire_brut: float,
    lignes_cotisations: List[Dict[str, Any]],
    total_cotisations_salariales: float,
    primes_non_soumises: List[Dict[str, Any]],
    remuneration_heures_supp: float # <-- NOUVEAU: On ajoute l'argument ici
) -> Dict[str, float]:
    print("INFO: Démarrage du calcul des nets et de l'impôt...", file=sys.stderr)
    
    net_social = round(_get_safe_float(salaire_brut) - _get_safe_float(total_cotisations_salariales), 2)
    
    # MODIFIÉ: On passe la nouvelle variable à la fonction de calcul
    net_imposable = _calculer_net_imposable(
        contexte, 
        salaire_brut, 
        total_cotisations_salariales, 
        lignes_cotisations,
        remuneration_heures_supp
    )
    
    montant_impot = _calculer_prelevement_a_la_source(contexte, net_imposable)
    net_a_payer = _calculer_net_a_payer(net_social, montant_impot, contexte, primes_non_soumises)
    
    print("INFO: Calcul des nets et de l'impôt terminé.", file=sys.stderr)
    return {"net_social": net_social, "net_imposable": net_imposable, "montant_impot_pas": montant_impot, "net_a_payer": net_a_payer}