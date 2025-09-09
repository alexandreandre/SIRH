# moteur_paie/calcul_brut.py

import sys
from .contexte import ContextePaie
from datetime import datetime, date, timedelta
from typing import Dict, Any, List
from .calcul_conges import calculer_indemnite_conges

def _get_salaire_horaire_base(contexte: ContextePaie, duree_hebdo_reelle: float) -> float:
    # Cette fonction reste inchangée
    salaire_mensuel = contexte.salaire_base_mensuel
    duree_legale_hebdo = 35.0
    if duree_hebdo_reelle <= duree_legale_hebdo:
        heures_mensuelles = round((duree_hebdo_reelle * 52) / 12, 2)
        return salaire_mensuel / heures_mensuelles if heures_mensuelles > 0 else 0.0
    heures_mensuelles_legales = round((duree_legale_hebdo * 52) / 12, 2)
    heures_sup_structurelles_mensuelles = round(((duree_hebdo_reelle - duree_legale_hebdo) * 52) / 12, 2)
    majoration_hs = contexte.baremes.get('heures_supp', {}).get('regles_calcul_communes', {}).get('taux_majoration_par_defaut', {}).get('heures_supplementaires', [{}])[0].get('taux', 0.25)
    heures_equivalentes_majorees = heures_mensuelles_legales + (heures_sup_structurelles_mensuelles * (1 + majoration_hs))
    return salaire_mensuel / heures_equivalentes_majorees if heures_equivalentes_majorees > 0 else 0.0

def _construire_ligne_avantages_en_nature(contexte: ContextePaie) -> Dict[str, Any] | None:
    # Cette fonction reste inchangée
    total_avantages = 0.0
    regles_aen = contexte.entreprise.get('parametres_paie', {}).get('avantages_en_nature', {})
    situation_salarie_aen = contexte.contrat.get('remuneration', {}).get('avantages_en_nature', {})
    situation_repas = situation_salarie_aen.get('repas', {})
    if situation_repas.get('nombre_par_mois', 0) > 0:
        valeur_forfaitaire_repas = regles_aen.get('repas_valeur_forfaitaire', 0.0)
        total_avantages += situation_repas['nombre_par_mois'] * valeur_forfaitaire_repas
    situation_logement = situation_salarie_aen.get('logement', {})
    if situation_logement.get('beneficie'):
        bareme_logement = regles_aen.get('logement_bareme_forfaitaire', [])
        salaire_mensuel = contexte.salaire_base_mensuel
        nb_pieces = situation_logement.get('nombre_pieces_principales', 1)
        for tranche in bareme_logement:
            if salaire_mensuel <= tranche.get('remuneration_max', float('inf')):
                valeur = tranche['valeur_1_piece']
                if nb_pieces > 1: valeur += tranche['valeur_par_piece'] * (nb_pieces - 1)
                total_avantages += valeur
                break
    if total_avantages > 0:
        return {"libelle": "Avantages en nature", "quantite": None, "taux": None, "gain": round(total_avantages, 2), "perte": None}
    return None

def _calculer_prime_anciennete(contexte: ContextePaie) -> Dict[str, Any] | None:
    # Cette fonction reste inchangée
    date_entree_str = contexte.contrat.get('contrat', {}).get('date_entree')
    if not date_entree_str: return None
    date_entree = datetime.strptime(date_entree_str, "%Y-%m-%d")
    anciennete_annees = (datetime.now() - date_entree).days / 365.25
    idcc = contexte.contrat.get('remuneration', {}).get('convention_collective', {}).get('idcc')
    if not idcc: return None
    regles_cc = contexte.baremes.get('conventions_collectives', {}).get(f"idcc_{idcc}", {})
    regles_prime = regles_cc.get('prime_anciennete', {})
    taux_applicable = 0.0
    for palier in regles_prime.get('bareme', []):
        if palier['annees_min'] <= anciennete_annees:
            taux_applicable = palier.get('taux', 0.0)
    if taux_applicable == 0.0: return None
    base_de_calcul = 0.0
    regle_base = regles_prime.get('base_de_calcul', {})
    methode = regle_base.get('methode')
    if methode == "salaire_minimum_conventionnel":
        coeff_salarie = contexte.contrat.get('remuneration', {}).get('classification_conventionnelle', {}).get('coefficient')
        for minima in regles_cc.get('salaires_minima', []):
            if minima.get('coefficient') == coeff_salarie:
                base_de_calcul = minima.get('valeur', 0.0)
                break
    elif methode == "pourcentage_salaire_de_base":
        pourcentage = regle_base.get('valeur', 0.0)
        base_de_calcul = contexte.salaire_base_mensuel * pourcentage
    else:
        base_de_calcul = contexte.salaire_base_mensuel
    if base_de_calcul == 0.0: return None
    montant_prime = base_de_calcul * taux_applicable
    return {"libelle": f"Prime d'ancienneté ({anciennete_annees:.0f} ans, {taux_applicable * 100:.0f}%)","quantite": base_de_calcul,"taux": taux_applicable,"gain": round(montant_prime, 2),"perte": None}


def _calculer_hs_semaine(heures_travaillees: float, duree_contrat_hebdo: float, regles_majoration: List[Dict]) -> Dict[float, float]:
    """
    Calcule la répartition des heures supplémentaires pour UNE semaine.
    """
    heures_sup_semaine = max(0, heures_travaillees - duree_contrat_hebdo)
    if heures_sup_semaine == 0:
        return {}
    
    hs_par_taux = {}
    heures_restantes_a_ventiler = heures_sup_semaine
    
    # On prend en compte les HS structurelles déjà incluses dans la durée du contrat
    heures_structurelles = max(0, duree_contrat_hebdo - 35)
    
    # Le seuil de passage à 50% est après 8h au total (structurelles + conjoncturelles)
    seuil_majoration_max = 8.0 
    
    # On calcule combien d'heures à 25% on peut encore faire cette semaine
    heures_a_25_restantes = max(0, seuil_majoration_max - heures_structurelles)
    
    taux_25 = regles_majoration[0].get('taux', 0.25)
    taux_50 = regles_majoration[1].get('taux', 0.50)

    # On ventile les heures sup de la semaine
    heures_a_25 = min(heures_restantes_a_ventiler, heures_a_25_restantes)
    if heures_a_25 > 0:
        hs_par_taux[taux_25] = heures_a_25
        heures_restantes_a_ventiler -= heures_a_25
    
    if heures_restantes_a_ventiler > 0:
        hs_par_taux[taux_50] = heures_restantes_a_ventiler
        
    return hs_par_taux

def calculer_salaire_brut(
    contexte: ContextePaie, 
    calendrier_saisie: List[Dict[str, Any]], # Note: On passera calendrier_etendu ici
    periode: Dict[str, int],
    primes_saisies: List[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Calcule le salaire brut et retourne une structure détaillée de sa composition.
    """
    lignes_composants_brut = []
    duree_legale_hebdo = 35.0
    duree_contrat_hebdo = contexte.duree_hebdo_contrat
    salaire_contractuel = contexte.salaire_base_mensuel
    taux_horaire_de_base = _get_salaire_horaire_base(contexte, duree_contrat_hebdo)
    
    # 1. Décomposition du salaire contractuel (inchangé)
    heures_mensuelles_legales = round((duree_legale_hebdo * 52) / 12, 2)
    salaire_base_35h = heures_mensuelles_legales * taux_horaire_de_base
    lignes_composants_brut.append({"libelle": "Salaire de base", "quantite": heures_mensuelles_legales, "taux": round(taux_horaire_de_base, 4), "gain": round(salaire_base_35h, 2), "perte": None})
    remuneration_hs_structurelles = 0.0
    heures_sup_structurelles_mensuelles = 0.0
    if duree_contrat_hebdo > duree_legale_hebdo:
        remuneration_hs_structurelles = salaire_contractuel - salaire_base_35h
        heures_sup_structurelles_mensuelles = round(((duree_contrat_hebdo - duree_legale_hebdo) * 52) / 12, 2)
        taux_horaire_majore = remuneration_hs_structurelles / heures_sup_structurelles_mensuelles if heures_sup_structurelles_mensuelles > 0 else 0
        majoration_pct = (taux_horaire_majore / taux_horaire_de_base - 1) * 100 if taux_horaire_de_base > 0 else 0
        lignes_composants_brut.append({"libelle": f"Heures suppl. structurelles majorées à {majoration_pct:.0f}%", "quantite": heures_sup_structurelles_mensuelles, "taux": round(taux_horaire_majore, 4), "gain": round(remuneration_hs_structurelles, 2), "perte": None})
        lignes_composants_brut.append({"libelle": "SOUS-TOTAL SALAIRE CONTRACTUEL", "quantite": round(heures_mensuelles_legales + heures_sup_structurelles_mensuelles, 2), "taux": None, "gain": salaire_contractuel, "perte": None, "is_sous_total": True})

    # 2. Logique de congés (inchangée)
    jours_de_conges = sum(1 for jour in calendrier_saisie if jour.get('type') == 'conges_payes')
    if jours_de_conges > 0:
        resultat_conges = calculer_indemnite_conges(contexte, jours_de_conges, taux_horaire_de_base)
        lignes_composants_brut.append({"libelle": f"Absence congés payés ({resultat_conges['nombre_jours']} jours)","quantite": round(resultat_conges['total_heures_absence'], 2), "taux": None, "gain": None, "perte": resultat_conges['montant_retenue']})
        if resultat_conges["methode_retenue"] == "Maintien":
            lignes_composants_brut.append({"libelle": "Indemnité de congés payés (partie base)","quantite": round(resultat_conges['heures_base'], 2),"taux": round(taux_horaire_de_base, 4),"gain": resultat_conges['indemnite_maintien_base'], "perte": None})
            if resultat_conges['indemnite_maintien_hs'] > 0:
                majoration_hs = contexte.baremes.get('heures_supp', {}).get('regles_calcul_communes', {}).get('taux_majoration_par_defaut', {}).get('heures_supplementaires', [{}])[0].get('taux', 0.25)
                salaire_horaire_majore = taux_horaire_de_base * (1 + majoration_hs)
                lignes_composants_brut.append({"libelle": "Indemnité de congés payés (partie HS 25%)","quantite": round(resultat_conges['heures_hs'], 2),"taux": round(salaire_horaire_majore, 4),"gain": resultat_conges['indemnite_maintien_hs'], "perte": None})
        else:
            lignes_composants_brut.append({"libelle": "Indemnité de congés payés (règle du 1/10ème)","quantite": None, "taux": None, "gain": resultat_conges['montant_indemnite'], "perte": None})
    
    annee_paie, mois_paie = periode.get('annee'), periode.get('mois')
    
    # 1. Agréger les heures par semaine ISO (année, numéro_semaine)
    semaines = {}
    for jour in calendrier_saisie:
        if jour.get('type') == 'travail' and 'date_complete' in jour:
            jour_date = date.fromisoformat(jour['date_complete'])
            annee_iso, num_semaine_iso, _ = jour_date.isocalendar()
            
            cle_semaine = (annee_iso, num_semaine_iso)
            if cle_semaine not in semaines:
                semaines[cle_semaine] = {'heures': 0, 'jours': []}
            
            semaines[cle_semaine]['heures'] += jour.get('heures', 0)
            semaines[cle_semaine]['jours'].append(jour_date)

    # 2. Calculer les HS uniquement pour les semaines se terminant dans le mois de paie
    total_hs_par_taux = {}
    regles_majoration = contexte.baremes.get('heures_supp', {}).get('regles_calcul_communes', {}).get('taux_majoration_par_defaut', {}).get('heures_supplementaires', [])
    
    for cle_semaine, data_semaine in semaines.items():
        # Déterminer la date de fin de la semaine (le dimanche)
        dernier_jour_travaille_semaine = max(data_semaine['jours'])
        fin_de_semaine = dernier_jour_travaille_semaine + timedelta(days=6 - dernier_jour_travaille_semaine.weekday())

        # Appliquer la règle : on ne traite que les semaines se terminant dans le mois de paie
        if fin_de_semaine.month == mois_paie and fin_de_semaine.year == annee_paie:
            heures_travaillees = data_semaine['heures']
            hs_semaine = _calculer_hs_semaine(heures_travaillees, duree_contrat_hebdo, regles_majoration)
            
            for taux, heures in hs_semaine.items():
                total_hs_par_taux[taux] = total_hs_par_taux.get(taux, 0) + heures

    remuneration_hs_conjoncturelles = 0.0
    heures_sup_conjoncturelles = 0
    for taux, heures in total_hs_par_taux.items():
        heures_sup_conjoncturelles += heures
        taux_horaire_majore = taux_horaire_de_base * (1 + taux)
        montant = heures * taux_horaire_majore
        remuneration_hs_conjoncturelles += montant
        lignes_composants_brut.append({"libelle": f"Heures suppl. conjoncturelles majorées à {taux * 100:.0f}%", "quantite": round(heures, 2), "taux": round(taux_horaire_majore, 4), "gain": round(montant, 2), "perte": None})

    # 3. Primes et autres éléments (inchangé)
    ligne_prime_anciennete = _calculer_prime_anciennete(contexte)
    if ligne_prime_anciennete: lignes_composants_brut.append(ligne_prime_anciennete)
    if primes_saisies:
        for prime in primes_saisies:
            lignes_composants_brut.append({"libelle": prime.get('libelle', 'Prime'), "quantite": None, "taux": None, "gain": prime.get('montant', 0.0), "perte": None})
    ligne_aen = _construire_ligne_avantages_en_nature(contexte)
    if ligne_aen: lignes_composants_brut.append(ligne_aen)
    
    # 4. Calcul des totaux (inchangé)
    total_gains = sum(ligne.get('gain', 0.0) or 0.0 for ligne in lignes_composants_brut if not ligne.get('is_sous_total'))
    total_pertes = sum(ligne.get('perte', 0.0) or 0.0 for ligne in lignes_composants_brut)
    total_brut = total_gains - total_pertes
    remuneration_hs_totale = remuneration_hs_structurelles + remuneration_hs_conjoncturelles
    total_heures_supp_mois = heures_sup_structurelles_mensuelles + heures_sup_conjoncturelles
    
    return {
        "salaire_brut_total": round(total_brut, 2),
        "lignes_composants_brut": lignes_composants_brut,
        "remuneration_brute_heures_supp": round(remuneration_hs_totale, 2),
        "total_heures_supp": round(total_heures_supp_mois, 2)
    }