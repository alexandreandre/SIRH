# generateur_fiche_paie.py

import json
from datetime import datetime, date # <-- Assurez-vous que 'date' est bien importé

# --- FONCTIONS D'AFFICHAGE (INCHANGÉES) ---
def print_header(entreprise, contrat):
    """Affiche l'en-tête du bulletin de paie."""
    date_entree_str = datetime.strptime(contrat['poste']['date_entree'], '%Y-%m-%d').strftime('%d/%m/%Y')
    print("\n" + "╔" + "═"*93 + "╗")
    print(f"║{'BULLETIN DE PAIE - Période du 01/08/2025 au 31/08/2025':^93}║")
    print("╠" + "═"*46 + "╦" + "═"*46 + "╣")
    print(f"║{'Employeur':^46}║{'Salarié':^46}║")
    print("╠" + "═"*46 + "╬" + "═"*46 + "╣")
    print(f"║ Raison Sociale : {entreprise['identite']['raison_sociale']:<29} ║ Nom : {contrat['identite']['nom']}, {contrat['identite']['prenom']:<34} ║")
    print(f"║ SIRET : {entreprise['identite']['siret']:<36} ║ N° SS : {contrat['identite'].get('num_ss', ''):<36} ║")
    print(f"║ Adresse : {entreprise['identite']['adresse']:<34} ║ Adresse : {contrat['identite'].get('adresse', ''):<34} ║")
    print(f"║ Code NAF (APE) : {entreprise['identite']['code_naf_ape']:<27} ║ Emploi : {contrat['poste']['emploi']:<35} ║")
    print(f"║ Convention Collective : {entreprise['identite']['convention_collective']:<21} ║ Classification : {contrat['poste'].get('classification', ''):<27} ║")
    print(f"║{'':<46}║ Date d'entrée : {date_entree_str:<28} ║")
    print("╚" + "═"*46 + "╩" + "═"*46 + "╝")

def print_remuneration_brute(data):
    """Affiche le tableau de la rémunération brute."""
    print("\n" + "╔" + "═"*93 + "╗")
    print(f"║{'Détail de la Rémunération Brute':^93}║")
    print("╠" + "═"*40 + "╦" + "═"*15 + "╦" + "═"*15 + "╦" + "═"*19 + "╣")
    print(f"║ {'Libellé':<39} ║ {'Base':^15} ║ {'Taux / Qté':^15} ║ {'Montant (€)':^19} ║")
    print("╠" + "═"*40 + "╬" + "═"*15 + "╬" + "═"*15 + "╬" + "═"*19 + "╣")
    print(f"║ {'Salaire de base mensuel':<39} ║ {data['horaire_mensuel']:.2f} h{'':<8} ║ {data['taux_horaire']:.2f} €{'':<8} ║ {data['salaire_base']:>18.2f} ║")
    if data.get('prime_anciennete', 0) > 0:
        print(f'''║ {"Prime d'ancienneté":<39} ║ {data['salaire_base']:.2f} €{'':<6} ║ {"5.00 %":^15} ║ {data['prime_anciennete']:>18.2f} ║''')
    if data.get('montant_heures_sup', 0) > 0:
        print(f"║ {'Heures supplémentaires (maj. 25%)':<39} ║ {data['heures_sup']:.2f} h{'':<8} ║ {data['taux_horaire_majore']:.2f} €{'':<8} ║ {data['montant_heures_sup']:>18.2f} ║")
    if data.get('prime_qualite', 0) > 0:
        print(f"║ {'Prime de qualité et de sécurité':<39} ║ {'Forfait':^15} ║ {'':^15} ║ {data['prime_qualite']:>18.2f} ║")
    if data.get('avantage_logement', 0) > 0:
        print(f"║ {'Avantage en nature : Logement':<39} ║ {data['avantage_logement_pieces']} pièce(s){'':<2} ║ {'Barème':^15} ║ {data['avantage_logement']:>18.2f} ║")
    if data.get('deduction_absence', 0) > 0:
        print(f"║ {'Absence non rémunérée':<39} ║ {data['heures_absence']:.2f} h{'':<8} ║ {data['taux_horaire']:.2f} €{'':<8} ║ {-data['deduction_absence']:18.2f} ║")
    print("╠" + "═"*40 + "╩" + "═"*15 + "╩" + "═"*15 + "╩" + "═"*19 + "╣")
    print(f"║{'SALAIRE BRUT TOTAL':>72} {data['salaire_brut']:>18.2f} € ║")
    print("╚" + "═"*93 + "╝")

def print_cotisations(details_cotisations, tot_sal, tot_pat, reduc_gen):
    """Affiche le tableau des cotisations sociales."""
    print("\n" + "╔" + "═"*105 + "╗")
    print(f"║{'Cotisations et Contributions Sociales':^105}║")
    print("╠" + "═"*40 + "╦" + "═"*12 + "╦" + "═"*12 + "╦" + "═"*12 + "╦" + "═"*12 + "╦" + "═"*12 + "╣")
    print(f"║ {'Contribution':<39} ║ {'Base (€)':^12} ║ {'Tx Sal.':^12} ║ {'Mt. Sal.':^12} ║ {'Tx Pat.':^12} ║ {'Mt. Pat.':^12} ║")
    print("╠" + "═"*40 + "╬" + "═"*12 + "╬" + "═"*12 + "╬" + "═"*12 + "╬" + "═"*12 + "╬" + "═"*12 + "╣")
    for item in details_cotisations:
        tx_sal_str = f"{item['tx_sal']*100:.2f}%" if isinstance(item['tx_sal'], float) else 'Forfait' if item['mt_sal'] != 0 else '-'
        tx_pat_str = f"{item['tx_pat']*100:.2f}%" if isinstance(item['tx_pat'], float) else 'Forfait' if item['mt_pat'] != 0 else '-'
        print(f"║ {item['libelle']:<39} ║ {item['base']:>10.2f} ║ {tx_sal_str:^12} ║ {item['mt_sal']:>10.2f} ║ {tx_pat_str:^12} ║ {item['mt_pat']:>10.2f} ║")
    print("╠" + "═"*40 + "╩" + "═"*12 + "╩" + "═"*12 + "╩" + "═"*12 + "╩" + "═"*12 + "╩" + "═"*12 + "╣")
    print(f"║{'TOTAL COTISATIONS':>68} {tot_sal:>10.2f} ║ {'':^12} ║ {tot_pat - reduc_gen:>10.2f} ║")
    if reduc_gen < 0:
        print(f"║{'Réduction générale de cotisations patronales':>91} {reduc_gen:>10.2f} ║")
    print("╠" + "═"*79 + "╦" + "═"*25 + "╣")
    print(f"║{'TOTAL CHARGES PATRONALES':>79}║ {tot_pat:>23.2f} ║")
    print("╚" + "═"*79 + "╩" + "═"*25 + "╝")

def print_net_a_payer(data):
    """Affiche le décompte du net à payer et du net versé."""
    print("\n" + "╔" + "═"*60 + "╗")
    print(f"║{'Net à Payer et Net Versé':^60}║")
    print("╠" + "═"*60 + "╣")
    print(f"║ {'Salaire Brut':<45} {data['salaire_brut']:>12.2f} € ║")
    print(f"║ {'(-) Total des cotisations salariales':<45} {-data['total_cotisations_salariales']:12.2f} € ║")
    print("╠" + "═"*60 + "╣")
    print(f"║ {'= NET À PAYER AVANT IMPÔT':<45} {data['net_avant_impot']:>12.2f} € ║")
    print("╠" + "═"*60 + "╣")
    print(f"║ {'IMPÔT SUR LE REVENU':<60} ║")
    print(f"║   Base du prélèvement à la source (PAS) : {data['net_imposable']:.2f} €{'':<15} ║")
    print(f"║   Taux de prélèvement (personnalisé) : {data['taux_pas']*100:.2f}%{'':<22} ║")
    print(f"║ {'(-) Montant du prélèvement à la source':<45} {-data['montant_pas']:12.2f} € ║")
    print("╠" + "═"*60 + "╣")
    print(f"║ {'= NET À PAYER':<45} {data['net_a_payer']:>12.2f} € ║")
    
    if data.get('total_indemnites', 0) > 0:
        print("╠" + "═"*60 + "╣")
        print(f"║ {'INDEMNITÉS DE FRAIS PROFESSIONNELS':<60} ║")
        if data['indemnites_details'].get('repas', 0) > 0:
            print(f"║   - Indemnité de repas : {data['indemnites_details']['repas']:.2f} €{'':<29} ║")
        if data['indemnites_details'].get('petit_deplacement', 0) > 0:
            print(f"║   - Petit déplacement : {data['indemnites_details']['petit_deplacement']:.2f} €{'':<26} ║")
        if data['indemnites_details'].get('teletravail', 0) > 0:
            print(f"║   - Télétravail : {data['indemnites_details']['teletravail']:.2f} €{'':<30} ║")
        print(f"║ {'(+) Total des indemnités':<45} {data['total_indemnites']:>12.2f} € ║")

    if data.get('montant_saisi', 0) > 0:
        print(f"║ {'(-) Saisie sur salaire':<45} {-data['montant_saisi']:12.2f} € ║")
    print("╠" + "═"*60 + "╣")
    print(f"║ {'MONTANT NET VERSÉ':<45} {data['net_verse']:>12.2f} € ║")
    print("╚" + "═"*60 + "╝")

def print_footer(cumuls, conges):
    """Affiche le pied de page avec les cumuls et congés."""
    print("\n" + "╔" + "═"*46 + "╦" + "═"*46 + "╗")
    print(f"║{'Cumuls Annuels (01/01 au 31/08/2025)':^46}║{'Compteur de Congés Payés (en jours)':^46}║")
    print("╠" + "═"*46 + "╬" + "═"*46 + "╣")
    print(f"║ Brut : {cumuls['brut']:<20.2f} €{'':<15} ║ Solde antérieur : {conges['solde_anterieur']:<26.2f} ║")
    print(f"║ Net Imposable : {cumuls['net_imposable']:<20.2f} €{'':<8} ║ Acquis du mois : +{conges['acquis_mois']:<25.2f} ║")
    print(f"║{'':<46}║ Pris dans le mois : -{conges['pris_mois']:<24.2f} ║")
    print("╠" + "═"*46 + "╬" + "═"*46 + "╣")
    print(f"║{'':<46}║ Nouveau Solde : {conges['nouveau_solde']:<30.2f} ║")
    print("╚" + "═"*46 + "╩" + "═"*46 + "╝")


def generer_fiche_paie():
    # --- 1. CHARGEMENT DE TOUTES LES CONFIGURATIONS ---
    try:
        with open('config/taux_cotisations.json', 'r', encoding='utf-8') as f:
            taux_cotisations = json.load(f)['TAUX_COTISATIONS']
        with open('config/parametres_contrat.json', 'r', encoding='utf-8') as f:
            contrat = json.load(f)['PARAMETRES_CONTRAT']
        with open('config/parametres_entreprise.json', 'r', encoding='utf-8') as f:
            entreprise = json.load(f)['PARAMETRES_ENTREPRISE']
        with open('config/baremes.json', 'r', encoding='utf-8') as f:
            baremes = json.load(f)['FRAIS_PROFESSIONNELS_2025']
    except Exception as e:
        print(f"Erreur lors du chargement des fichiers de configuration : {e}")
        return

    # --- 2. CALCULS PRÉLIMINAIRES ---
    salaire_base = contrat['remuneration']['taux_horaire'] * contrat['remuneration']['horaire_mensuel']
    annees_anciennete = (datetime.now() - datetime.strptime(contrat['poste']['date_entree'], "%Y-%m-%d")).days / 365.25
    prime_anciennete = salaire_base * 0.05 if annees_anciennete >= 5 else 0
    taux_horaire_majore_25 = contrat['remuneration']['taux_horaire'] * 1.25
    montant_heures_sup = contrat['variables_du_mois']['heures_supplementaires_majoration_25'] * taux_horaire_majore_25
    heures_absence = contrat['variables_du_mois']['jours_absence_non_remuneree'] * contrat['variables_du_mois']['heures_par_jour_travaille']
    deduction_absence = heures_absence * contrat['remuneration']['taux_horaire']

    # --- 2.1. Calcul des avantages en nature ---
    montant_avantage_logement = 0
    nb_pieces = contrat['variables_du_mois'].get('avantage_logement_nb_pieces', 0)
    if nb_pieces > 0 and 'AVANTAGES_EN_NATURE_2025' in baremes:
        bareme_logement = baremes['AVANTAGES_EN_NATURE_2025'].get('logement_bareme_forfaitaire', [])
        salaire_de_reference = salaire_base
        for tranche in bareme_logement:
            rem_max = float('inf') if tranche.get('remuneration_max') == 'inf' else tranche.get('remuneration_max', 0)
            if salaire_de_reference <= rem_max:
                montant_avantage_logement = tranche.get('valeur_1_piece', 0) if nb_pieces == 1 else tranche.get('valeur_par_piece', 0) * nb_pieces
                break

    # --- 3. CALCUL DU SALAIRE BRUT ---
    salaire_brut_habituel = (salaire_base + prime_anciennete + montant_heures_sup + 
                             contrat['variables_du_mois']['prime_qualite_securite'] +
                             montant_avantage_logement)
    salaire_brut = salaire_brut_habituel - deduction_absence
                    
    # --- 4. CALCUL DES COTISATIONS ET DE LA RÉDUCTION GÉNÉRALE ---

    # ANCIEN CODE :
    # smic_horaire = entreprise['constantes_paie_2025']['smic_horaire']['cas_general']
    
    # NOUVEAU BLOC DE LOGIQUE :
    
    # a. Calculer l'âge et l'ancienneté du salarié
    date_naissance = datetime.strptime(contrat['identite']['date_naissance'], '%Y-%m-%d').date()
    date_paie = date(2025, 8, 31) # Date de fin de la période de paie
    age = date_paie.year - date_naissance.year - ((date_paie.month, date_paie.day) < (date_naissance.month, date_naissance.day))
    
    annees_anciennete = (date_paie - datetime.strptime(contrat['poste']['date_entree'], "%Y-%m-%d").date()).days / 365.25

    # b. Sélectionner le SMIC horaire applicable
    smic_horaires_bareme = entreprise['constantes_paie_2025']['smic_horaire']
    
    # Par défaut, on applique le SMIC général
    smic_horaire = smic_horaires_bareme['cas_general']
    
    # Condition pour appliquer un SMIC minoré : jeune de moins de 18 ans ET moins de 6 mois d'ancienneté
    if age < 18 and annees_anciennete < 0.5:
        if age < 17:
            smic_horaire = smic_horaires_bareme['moins_de_17_ans']
            print("INFO: Application du SMIC pour salarié de moins de 17 ans.")
        else: # L'âge est de 17 ans
            smic_horaire = smic_horaires_bareme['entre_17_et_18_ans']
            print("INFO: Application du SMIC pour salarié entre 17 et 18 ans.")
    
    smic_mensuel_base = smic_horaire * (35 * 52 / 12)
    smic_ajuste = smic_mensuel_base
    duree_hebdomadaire_contrat = contrat['remuneration'].get('duree_hebdomadaire', 35)
    if duree_hebdomadaire_contrat < 35:
        smic_ajuste = smic_mensuel_base * (duree_hebdomadaire_contrat / 35)
    if deduction_absence > 0 and salaire_brut_habituel > 0:
        smic_ajuste = smic_ajuste * (salaire_brut / salaire_brut_habituel)
    parametre_T = entreprise['constantes_paie_2025']['parametre_T_reduction_generale']
    reduction_generale = 0
    if salaire_brut > 0 and smic_ajuste > 0 and salaire_brut < (1.6 * smic_ajuste):
        coefficient_C = (parametre_T / 0.6) * (1.6 * smic_ajuste / salaire_brut - 1)
        coefficient_C = min(coefficient_C, parametre_T)
        reduction_generale = - (coefficient_C * salaire_brut)

    plafond_ss = entreprise['constantes_paie_2025']['plafonds_securite_sociale']['mensuel']
    base_csg_crds = salaire_brut * 0.9825
    total_cotisations_salariales, total_cotisations_patronales, details_cotisations = 0, 0, []
    for code, info in taux_cotisations.items():
        base_calcul = 0
        if info.get('base') == 'brut': base_calcul = salaire_brut
        elif info.get('base') == 'plafond_ss': base_calcul = min(salaire_brut, plafond_ss)
        elif info.get('base') == 'csg_crds': base_calcul = base_csg_crds
        elif info.get('base') == 'heures_sup': base_calcul = montant_heures_sup
        
        taux_salarial = info.get('salarial') or 0
        fixe_salarial = info.get('salarial_fixe') or 0
        taux_patronal = info.get('patronal') or 0
        fixe_patronal = info.get('patronal_fixe') or 0

        montant_salarial = base_calcul * taux_salarial + fixe_salarial
        montant_patronal = base_calcul * taux_patronal + fixe_patronal
        
        total_cotisations_salariales += montant_salarial
        total_cotisations_patronales += montant_patronal
        details_cotisations.append({'libelle': info['libelle'], 'base': base_calcul, 'tx_sal': info.get('salarial', '-'), 'mt_sal': montant_salarial, 'tx_pat': info.get('patronal', '-'), 'mt_pat': montant_patronal})

    cotisation_at = salaire_brut * entreprise['conditions_cotisations']['taux_accident_travail']
    total_cotisations_patronales += cotisation_at
    details_cotisations.insert(2, {'libelle': 'Cotisation Accidents du travail', 'base': salaire_brut, 'tx_sal': '-', 'mt_sal': 0, 'tx_pat': entreprise['conditions_cotisations']['taux_accident_travail'], 'mt_pat': cotisation_at})
    total_cotisations_patronales += reduction_generale

    # --- 5. CALCUL DU NET ---
    net_avant_impot = salaire_brut - total_cotisations_salariales
    
    # --- LIGNES CORRIGÉES ---
    taux_csg_non_ded = taux_cotisations.get('csg_crds_non_deductible', {}).get('salarial') or 0
    csg_crds_non_deductible = base_csg_crds * taux_csg_non_ded
    
    part_patronale_mutuelle = taux_cotisations.get('sante_mutuelle', {}).get('patronal_fixe') or 0
    # --- FIN DES CORRECTIONS ---
    
    net_imposable = net_avant_impot + csg_crds_non_deductible + part_patronale_mutuelle
    montant_pas = net_imposable * contrat['imposition']['taux_pas']
    net_a_payer = net_avant_impot - montant_pas
    
    # --- 5.1. Calcul des indemnités de frais professionnels ---
    total_indemnites = 0
    indemnites_details = {}
    frais_pro_baremes = baremes.get('FRAIS_PROFESSIONNELS_2025', {})
    
    nb_repas_resto = contrat['variables_du_mois'].get('frais_repas_restaurant', 0)
    if nb_repas_resto > 0 and frais_pro_baremes.get('repas_indemnites'):
        montant = nb_repas_resto * frais_pro_baremes['repas_indemnites'].get('hors_locaux_avec_restaurant', 0)
        indemnites_details['repas'] = montant
        total_indemnites += montant
    
    km_deplacement = contrat['variables_du_mois'].get('frais_petit_deplacement_km', 0)
    if km_deplacement > 0 and frais_pro_baremes.get('petit_deplacement_bareme'):
        montant = 0
        for tranche in frais_pro_baremes['petit_deplacement_bareme']:
            if tranche['km_min'] <= km_deplacement < tranche['km_max']:
                montant = tranche['montant']
                break
        if contrat['variables_du_mois'].get('vehicule_electrique', False):
            montant *= 1.20
        indemnites_details['petit_deplacement'] = montant
        total_indemnites += montant

    jours_teletravail = contrat['variables_du_mois'].get('jours_teletravail', 0)
    if jours_teletravail > 0 and frais_pro_baremes.get('teletravail'):
        bareme_tt = frais_pro_baremes['teletravail'].get('indemnite_sans_accord', {})
        montant = jours_teletravail * bareme_tt.get('par_jour', 0)
        montant = min(montant, bareme_tt.get('limite_mensuelle', montant))
        indemnites_details['teletravail'] = montant
        total_indemnites += montant

    # --- 5.2. Calcul de la saisie sur salaire ---
    montant_saisi = 0
    saisie_info_baremes = baremes.get('SAISIE_SUR_SALAIRE_2025', {})
    if contrat['imposition'].get('saisie_arret_active', False) and saisie_info_baremes:
        bareme_saisie = saisie_info_baremes.get('bareme_mensuel', [])
        sbi = saisie_info_baremes.get('solde_bancaire_insaisissable', 0)
        personnes_a_charge = contrat['imposition'].get('personnes_a_charge_saisie', 0)
        
        salaire_net_saisissable = net_avant_impot 
        montant_saisissable_calcule, seuil_precedent = 0, 0
        majoration_par_personne = 143.33 
        
        for tranche in bareme_saisie:
            plafond_tranche = float('inf') if tranche['tranche_plafond'] is None else tranche['tranche_plafond']
            plafond_tranche_majore = plafond_tranche + (personnes_a_charge * majoration_par_personne)
            
            if salaire_net_saisissable > seuil_precedent:
                montant_dans_tranche = min(salaire_net_saisissable, plafond_tranche_majore) - seuil_precedent
                part_saisie = montant_dans_tranche * tranche['quotite_saisissable']
                montant_saisissable_calcule += part_saisie
            seuil_precedent = plafond_tranche_majore
        
        montant_saisi = min(montant_saisissable_calcule, salaire_net_saisissable - sbi)
        if montant_saisi < 0: montant_saisi = 0

    net_verse = net_a_payer + total_indemnites - montant_saisi
    
    # --- 6. MISE À JOUR DES COMPTEURS ---
    jours_conges_pris_mois = contrat['variables_du_mois'].get('jours_conges_payes_pris', 0)
    nouveau_solde_conges = contrat['compteurs']['conges_solde_anterieur'] + contrat['compteurs']['conges_acquis_par_mois'] - jours_conges_pris_mois
    cumul_brut_final = contrat['compteurs']['cumul_brut_annuel_debut_periode'] + salaire_brut
    cumul_net_imposable_final = contrat['compteurs']['cumul_net_imposable_annuel_debut_periode'] + net_imposable

    # --- 7. AFFICHAGE DU BULLETIN ---
    print_header(entreprise, contrat)
    print_remuneration_brute({
        'horaire_mensuel': contrat['remuneration']['horaire_mensuel'], 'taux_horaire': contrat['remuneration']['taux_horaire'],
        'salaire_base': salaire_base, 'prime_anciennete': prime_anciennete, 'heures_sup': contrat['variables_du_mois']['heures_supplementaires_majoration_25'],
        'taux_horaire_majore': taux_horaire_majore_25, 'montant_heures_sup': montant_heures_sup, 'prime_qualite': contrat['variables_du_mois']['prime_qualite_securite'],
        'heures_absence': heures_absence, 'deduction_absence': deduction_absence, 'salaire_brut': salaire_brut,
        'avantage_logement': montant_avantage_logement, 'avantage_logement_pieces': nb_pieces
    })
    print_cotisations(details_cotisations, total_cotisations_salariales, total_cotisations_patronales, reduction_generale)
    print_net_a_payer({
        'salaire_brut': salaire_brut, 'total_cotisations_salariales': total_cotisations_salariales, 'net_avant_impot': net_avant_impot,
        'net_imposable': net_imposable, 'taux_pas': contrat['imposition']['taux_pas'], 'montant_pas': montant_pas, 'net_a_payer': net_a_payer,
        'total_indemnites': total_indemnites, 'indemnites_details': indemnites_details,
        'net_verse': net_verse, 'montant_saisi': montant_saisi
    })
    print_footer(
        {'brut': cumul_brut_final, 'net_imposable': cumul_net_imposable_final},
        {'solde_anterieur': contrat['compteurs']['conges_solde_anterieur'], 'acquis_mois': contrat['compteurs']['conges_acquis_par_mois'],
         'pris_mois': jours_conges_pris_mois, 'nouveau_solde': nouveau_solde_conges}
    )

if __name__ == "__main__":
    generer_fiche_paie()