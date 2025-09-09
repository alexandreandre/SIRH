# generateur_fiche_paie.py

import json
import sys
import traceback
from pathlib import Path
from datetime import date, timedelta  
# Imports pour la génération PDF
from jinja2 import Environment, FileSystemLoader
from weasyprint import HTML

# Imports pour le moteur de calcul
from moteur_paie.contexte import ContextePaie
from moteur_paie.calcul_brut import calculer_salaire_brut
from moteur_paie.calcul_cotisations import calculer_cotisations
from moteur_paie.calcul_reduction_generale import calculer_reduction_generale
from moteur_paie.calcul_net import calculer_net_et_impot
from moteur_paie.bulletin import creer_bulletin_final

def mettre_a_jour_cumuls(
    contexte: ContextePaie,
    salaire_brut_mois: float,
    remuneration_hs_mois: float,
    resultats_nets_mois: dict,
    reduction_generale_mois: dict,
    saisie_horaires: dict,
    smic_mois: float,
    pss_mois: float,
    chemin_employe: Path 
):
    """
    Lit le fichier cumuls.json du mois précédent, y ajoute les valeurs du mois,
    et écrit un nouveau fichier cumuls_[mois].json.
    """
    print("INFO: Création du nouveau fichier de cumuls annuels...", file=sys.stderr)
    
    cumuls_data = contexte.cumuls
    nouveaux_cumuls_data = json.loads(json.dumps(cumuls_data))
    
    mois_actuel = saisie_horaires.get('periode', {}).get('mois')
    nouveau_fichier_path = chemin_employe / f'cumuls_{mois_actuel}.json'

    nouveaux_cumuls_data['periode']['dernier_mois_calcule'] = mois_actuel
    
    cumuls = nouveaux_cumuls_data['cumuls']
    cumuls['brut_total'] += round(salaire_brut_mois, 2)
    cumuls['net_imposable'] += round(resultats_nets_mois.get('net_imposable', 0.0), 2)
    cumuls['impot_preleve_a_la_source'] += round(resultats_nets_mois.get('montant_impot_pas', 0.0), 2)
    cumuls['heures_supplementaires_remunerees'] += round(remuneration_hs_mois, 2)
    cumuls['smic_calcule'] += round(smic_mois, 2)
    cumuls['plafond_securite_sociale'] += round(pss_mois, 2)
    
    if reduction_generale_mois:
        cumuls['reduction_generale_patronale'] += round(reduction_generale_mois.get('montant_patronal', 0.0), 2)

    with open(nouveau_fichier_path, 'w', encoding='utf-8') as f:
        json.dump(nouveaux_cumuls_data, f, indent=2, ensure_ascii=False)
        
    print(f"✅ Fichier {nouveau_fichier_path} créé avec les cumuls à jour.", file=sys.stderr)

def creer_calendrier_etendu(chemin_employe: Path, annee: int, mois: int) -> list:
    """
    Charge le calendrier du mois et l'étend pour inclure les jours des mois
    précédent et suivant afin de former des semaines complètes (lundi-dimanche).
    """
    # Date du premier et du dernier jour du mois de paie
    premier_jour_mois = date(annee, mois, 1)
    dernier_jour_mois = date(annee, mois, 1) + timedelta(days=31)
    dernier_jour_mois = dernier_jour_mois.replace(day=1) - timedelta(days=1)

    # Trouver le lundi de la première semaine et le dimanche de la dernière
    debut_calendrier = premier_jour_mois - timedelta(days=premier_jour_mois.weekday())
    fin_calendrier = dernier_jour_mois + timedelta(days=6 - dernier_jour_mois.weekday())

    calendrier_final = []
    
    # Itérer sur chaque mois potentiellement concerné (M-1, M, M+1)
    for dt in [debut_calendrier, premier_jour_mois, fin_calendrier]:
        mois_a_charger = dt.month
        annee_a_charger = dt.year
        
        # Nom du fichier basé sur le mois et l'année (ex: horaires_07_2025.json)
        # Adaptez le nommage si nécessaire. Je suppose ici un format "horaires_MM_YYYY.json"
        # Si vous utilisez "horaires.json", il faudra adapter la logique de lecture.
        # Pour cet exemple, je vais simplifier et supposer un nommage "horaires_MM.json"
        # mais une vraie solution demanderait "horaires_MM_YYYY.json"
        nom_fichier = f"horaires_{mois_a_charger:02d}.json"
        chemin_fichier = chemin_employe / nom_fichier
        
        if chemin_fichier.exists():
            data = json.loads(chemin_fichier.read_text(encoding='utf-8'))
            for jour_data in data.get('calendrier', []):
                jour_date = date(annee_a_charger, mois_a_charger, jour_data['jour'])
                # N'ajouter que les jours dans notre fenêtre de calcul
                if debut_calendrier <= jour_date <= fin_calendrier:
                    # Enrichir chaque jour avec sa date complète pour faciliter le traitement
                    jour_data['date_complete'] = jour_date.isoformat()
                    calendrier_final.append(jour_data)

    # Trier et dédoublonner au cas où les fichiers se chevauchent
    calendrier_final = sorted(calendrier_final, key=lambda j: j['date_complete'])
    calendrier_unique = []
    vus = set()
    for jour in calendrier_final:
        if jour['date_complete'] not in vus:
            calendrier_unique.append(jour)
            vus.add(jour['date_complete'])
            
    return calendrier_unique

def generer_une_fiche_de_paie():
    """
    Fonction principale qui orchestre la génération complète d'une fiche de paie,
    du calcul des données jusqu'à la création du fichier PDF.
    """
    try:
        # --- BLOC DE CONFIGURATION ---
        nom_dossier_employe = "COTTE_Leo"
        chemin_employe = Path('data/employes') / nom_dossier_employe
        print(f"\n--- Calcul du bulletin pour l'employé : {nom_dossier_employe} ---", file=sys.stderr)
        # -----------------------------

        # Étape 0 : Chargement des variables du mois
        print("INFO: Chargement des variables du mois...", file=sys.stderr)
        # Note : On suppose que saisie_du_mois.json contient la période cible
        saisie_du_mois = json.loads((chemin_employe / 'saisie_du_mois.json').read_text(encoding='utf-8'))
        periode_actuelle = saisie_du_mois.get('periode', {})
        annee, mois = periode_actuelle['annee'], periode_actuelle['mois']

        saisie_horaires_mois_courant = json.loads((chemin_employe / f'horaires_{mois:02d}.json').read_text(encoding='utf-8'))
        calendrier_du_mois = saisie_horaires_mois_courant.get('calendrier', [])


        # Création du calendrier étendu pour un calcul juste des semaines
        calendrier_etendu = creer_calendrier_etendu(chemin_employe, annee, mois)


        # Étape 1 : Charger le contexte
        contexte = ContextePaie(
            chemin_contrat=chemin_employe / 'contrat.json',
            chemin_entreprise='data/entreprise.json',
            chemin_cumuls=chemin_employe / 'cumuls.json'
        )

        primes_soumises = []
        primes_non_soumises = []
        catalogue_primes = {p['id']: p for p in contexte.baremes['primes']}

        for prime_saisie in saisie_du_mois.get('primes', []):
            prime_id = prime_saisie.get('prime_id')
            regles = catalogue_primes.get(prime_id)
            if regles:
                prime_calculee = {"libelle": regles.get('libelle'), "montant": prime_saisie.get('montant')}
                if regles.get('soumise_a_cotisations'):
                    primes_soumises.append(prime_calculee)
                else:
                    primes_non_soumises.append(prime_calculee)
        
        # Étape 2 : Calculer le salaire brut
        # APPEL CORRIGÉ : On passe bien la variable 'periode_actuelle'
        resultat_brut = calculer_salaire_brut(
            contexte,
            calendrier_saisie=calendrier_etendu,
            periode=periode_actuelle,
            primes_saisies=primes_soumises
        )
        salaire_brut_calcule = resultat_brut['salaire_brut_total']
        details_brut = resultat_brut['lignes_composants_brut']
        remuneration_hs = resultat_brut['remuneration_brute_heures_supp']
        total_heures_supp = resultat_brut['total_heures_supp']
        print(f"INFO [generateur]: Salaire brut calculé = {salaire_brut_calcule} €", file=sys.stderr)

        # Étape 3 : Calculer les cotisations de base
        lignes_cotisations, total_salarial = calculer_cotisations(contexte, salaire_brut_calcule, remuneration_hs, total_heures_supp)
        print(f"INFO [generateur]: Total cotisations salariales (avant réductions) = {total_salarial} €", file=sys.stderr)

        # Étape 3.5 : Calculer la réduction générale et l'ajouter à la liste
        ligne_reduction_generale = calculer_reduction_generale(
            contexte, 
            salaire_brut_calcule,
            calendrier_du_mois
        )
        if ligne_reduction_generale:
            lignes_cotisations.append(ligne_reduction_generale)

        # Étape 4 : Calculer les valeurs nettes et l'impôt
        resultats_nets = calculer_net_et_impot(contexte, salaire_brut_calcule, lignes_cotisations, total_salarial, primes_non_soumises, remuneration_hs)
        print(f"INFO [generateur]: Net à payer calculé = {resultats_nets['net_a_payer']} €", file=sys.stderr)

        # Étape 5 : Assembler le bulletin de paie final
        bulletin_final = creer_bulletin_final(contexte, salaire_brut_calcule, details_brut, lignes_cotisations, resultats_nets, primes_non_soumises)
        
        # Étape Finale : Génération du PDF
        print("\nINFO: Génération du PDF...", file=sys.stderr)
        env = Environment(loader=FileSystemLoader('templates/'))
        template = env.get_template('template_bulletin.html')
        html_genere = template.render(bulletin_final)
        
        nom_salarie = bulletin_final['en_tete']['salarie']['nom_complet'].replace(' ', '_')
        mois_annee = f"{saisie_horaires_mois_courant['periode']['mois']:02d}-{saisie_horaires_mois_courant['periode']['annee']}"
        
        pdf_filename = chemin_employe / f"Bulletin_{nom_salarie}_{mois_annee}.pdf"
        
        HTML(string=html_genere, base_url='.').write_pdf(pdf_filename)

        print(f"✅ Bulletin de paie généré avec succès : {pdf_filename}", file=sys.stderr)

        # --- ÉTAPE 6 : MISE À JOUR DES CUMULS ---
        duree_contrat_hebdo = contexte.duree_hebdo_contrat
        jours_ouvrables_du_mois = sum(1 for jour in calendrier_du_mois if jour.get('type') not in ['weekend'])
        heures_theoriques_du_mois = jours_ouvrables_du_mois * (duree_contrat_hebdo / 5)
        jours_de_conges = sum(1 for jour in calendrier_du_mois if jour.get('type') == 'conges_payes')
        heures_dues_hors_conges = heures_theoriques_du_mois - (jours_de_conges * (duree_contrat_hebdo / 5))
        heures_travaillees_reelles = sum(j.get('heures', 0) for j in calendrier_du_mois if j.get('type') == 'travail')
        heures_sup_conjoncturelles_mois = max(0, heures_travaillees_reelles - heures_dues_hors_conges)
        heures_contractuelles_mois = round((duree_contrat_hebdo * 52) / 12, 2)
        total_heures_mois = heures_contractuelles_mois + heures_sup_conjoncturelles_mois

        smic_calcule_mois = contexte.baremes.get('smic', {}).get('cas_general', 0.0) * total_heures_mois
        pss_du_mois = contexte.baremes.get('pss', {}).get('mensuel', 0.0)

        mettre_a_jour_cumuls(
            contexte, salaire_brut_calcule, remuneration_hs, resultats_nets,
            ligne_reduction_generale, saisie_horaires_mois_courant, smic_calcule_mois, pss_du_mois,
            chemin_employe
        )
        
    except Exception as e:
        print(f"\nERREUR FATALE LORS DE LA GÉNÉRATION : {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    generer_une_fiche_de_paie()