# moteur_paie/bulletin.py

import sys
from datetime import datetime
from .contexte import ContextePaie
from typing import Dict, Any, List

def creer_bulletin_final(
    contexte: ContextePaie,
    salaire_brut: float,
    details_brut: List[Dict[str, Any]],
    lignes_cotisations: List[Dict[str, Any]],
    resultats_nets: Dict[str, float],
    primes_non_soumises: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Assemble tous les éléments calculés en une structure de données finale
    qui respecte l'ordre d'affichage désiré sur le bulletin.
    """
    print("INFO: Assemblage et tri du bulletin de paie final...", file=sys.stderr)
    
    # --- NOUVEAU : Séparation des lignes de congés payés du reste du brut ---
    lignes_conges = []
    autres_lignes_brut = []
    indemnite_conges = 0.0
    retenue_conges = 0.0

    for ligne in details_brut:
        libelle = ligne.get('libelle', '').lower()
        if 'conges payes' in libelle.replace('é', 'e'):
            lignes_conges.append(ligne)
            if 'indemnité' in libelle:
                indemnite_conges = ligne.get('gain', 0.0)
            if 'absence' in libelle:
                retenue_conges = ligne.get('perte', 0.0)
        else:
            autres_lignes_brut.append(ligne)
    
    # --- NOUVEAU : Préparation du texte pour l'arbitrage des congés payés ---
    texte_arbitrage = None
    if lignes_conges:
        if indemnite_conges > retenue_conges:
            texte_arbitrage = f"L'indemnité de congés payés a été calculée selon la règle du 1/10ème (soit {indemnite_conges:.2f} €), plus favorable que le maintien de salaire ({retenue_conges:.2f} €)."
        else:
            texte_arbitrage = f"L'indemnité de congés payés a été calculée selon la règle du maintien de salaire ({retenue_conges:.2f} €), plus favorable que la règle du 1/10ème."

    # --- Tri des cotisations en plusieurs blocs pour l'affichage ---
    bloc_principales = []
    bloc_allegements = []
    bloc_autres_contributions = []
    bloc_csg_non_deductible = []

    AUTRES_CONTRIBUTIONS_KEYWORDS = ['fnal', 'formation', 'apprentissage', 'solidarité', 'dialogue', 'mobilité']
    ALLEGEMENTS_KEYWORDS = ['réduction générale', 'réduction de cotisations sur heures sup', 'déduction forfaitaire']
    
    for ligne in lignes_cotisations:
        libelle = ligne.get('libelle', '').lower()
        
        if "csg/crds sur hs" in libelle or "csg/crds non déductible" in libelle :
            bloc_csg_non_deductible.append(ligne)
        elif any(keyword in libelle for keyword in ALLEGEMENTS_KEYWORDS):
            bloc_allegements.append(ligne)
        elif any(keyword in libelle for keyword in AUTRES_CONTRIBUTIONS_KEYWORDS):
            bloc_autres_contributions.append(ligne)
        else:
            bloc_principales.append(ligne)
            
    # --- Calcul des totaux ---
    total_autres_contributions = sum(l.get('montant_patronal', 0.0) or 0.0 for l in bloc_autres_contributions)
    total_cotisations_salariales = sum(l.get('montant_salarial', 0.0) or 0.0 for l in lignes_cotisations)
    total_cotisations_patronales = sum(l.get('montant_patronal', 0.0) or 0.0 for l in lignes_cotisations)
    
    total_retenues_avant_csg_nd = sum(l.get('montant_salarial', 0.0) or 0.0 for l in bloc_principales + bloc_allegements)
    total_patronal_avant_csg_nd = sum(l.get('montant_patronal', 0.0) or 0.0 for l in bloc_principales + bloc_allegements)
    
    total_primes_non_soumises = sum(p.get('montant', 0.0) or 0.0 for p in primes_non_soumises)

    # --- Assemblage du dictionnaire final ---
    bulletin = {
        "en_tete": {
            "periode": datetime.now().strftime("%B %Y"),
            "entreprise": {
                "raison_sociale": contexte.entreprise.get('identification', {}).get('raison_sociale'),
                "siret": contexte.entreprise.get('identification', {}).get('siret'),
                "adresse": contexte.entreprise.get('identification', {}).get('adresse')
            },
            "salarie": {
                "nom_complet": f"{contexte.contrat.get('salarie', {}).get('prenom')} {contexte.contrat.get('salarie', {}).get('nom')}",
                "nir": contexte.contrat.get('salarie', {}).get('nir'),
                "emploi": contexte.contrat.get('contrat', {}).get('emploi'),
                "statut": contexte.statut_salarie,
                "date_entree": contexte.contrat.get('contrat', {}).get('date_entree')
            }
        },
        # MODIFIÉ: On passe les nouvelles structures de données
        "details_conges": lignes_conges,
        "calcul_du_brut": autres_lignes_brut,
        "arbitrage_conges": texte_arbitrage,
        
        "salaire_brut": salaire_brut,
        "structure_cotisations": {
            "bloc_principales": bloc_principales,
            "bloc_allegements": bloc_allegements,
            "bloc_autres_contributions": {
                "lignes": bloc_autres_contributions,
                "total": round(total_autres_contributions, 2)
            },
            "total_avant_csg_crds": {
                "libelle": "Total des retenues (avant CSG/CRDS non déductible)",
                "montant_salarial": round(total_retenues_avant_csg_nd, 2),
                "montant_patronal": round(total_patronal_avant_csg_nd, 2)
            },
            "bloc_csg_non_deductible": bloc_csg_non_deductible,
            "total_salarial": round(total_cotisations_salariales, 2),
            "total_patronal": round(total_cotisations_patronales, 2)
        },
        "synthese_net": {
            "net_social_avant_impot": resultats_nets.get('net_social'),
            "net_imposable": resultats_nets.get('net_imposable'),
            "impot_prelevement_a_la_source": {
                "base": resultats_nets.get('net_imposable'),
                "taux": contexte.contrat.get('specificites_paie', {}).get('prelevement_a_la_source', {}).get('taux', 0.0),
                "montant": resultats_nets.get('montant_impot_pas')
            },
        },
        "primes_non_soumises": primes_non_soumises,
        "net_a_payer": resultats_nets.get('net_a_payer'),
        "pied_de_page": {
            "cout_total_employeur": round(salaire_brut + total_cotisations_patronales + total_primes_non_soumises, 2),
            "cumuls_annuels": {
                "_commentaire": "Ces valeurs seraient calculées sur la base des bulletins précédents.",
                "brut_cumule": 0.0,
                "net_imposable_cumule": 0.0,
                "heures_supplementaires_cumulees": 0
            }
        }
    }
    print("INFO: Bulletin de paie final assemblé.", file=sys.stderr)
    return bulletin