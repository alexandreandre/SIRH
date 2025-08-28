BULLETIN_DE_PAIE/
├─ __pycache__/
├─ config/
│  ├─ vides/
│  │  ├─ baremes_vide.json
│  │  ├─ parametres_contrat_vide.json
│  │  ├─ parametres_entreprise_vide.json
│  │  └─ taux_cotisations_vide.json
│  ├─ baremes.json
│  ├─ parametres_contrat.json
│  ├─ parametres_entreprise.json
│  └─ taux_cotisations.json
├─ HTML/
│  ├─ check_changement_du_html.py
│  ├─ check_changement_du_html_2.py
│  ├─ recup_html.py
│  ├─ page.html
│  ├─ page.remote.html
│  └─ tauxcotisations.html
├─ scripts/
│  ├─ AGS.py
│  ├─ alloc.py
│  ├─ assurancechomage.py
│  ├─ Avantages.py
│  ├─ calculT.py
│  ├─ CSA.py
│  ├─ CSG.py
│  ├─ FNAL.py
│  ├─ fraispro.py
│  ├─ IJmaladie.py
│  ├─ MMIDpatronal.py
│  ├─ MMIDsalarial.py
│  ├─ saisie-arret.py
│  ├─ SMIC.py
│  ├─ vider_json.py
│  ├─ vieillessepatronal.py
│  └─ vieillessesalarial.py
├─ venv/
├─ generateur_fiche_paie.py
├─ idcc.py
└─ README.md


generateur_fiche_paie.py : Génère la fiche de paie


Explication des dossiers :

📂 config/

Ce dossier contient les paramètres et taux utilisés pour générer les bulletins de paie.

parametres_contrat.json : définit les paramètres individuels du contrat (taux horaire, heures mensuelles, primes, mutuelle, PAS, indemnités).

parametres_entreprise.json : stocke les informations légales de l’entreprise (raison sociale, SIRET, adresse) et ses conditions de cotisations (effectif, seuils SMIC).

taux_cotisations.json : regroupe l’ensemble des taux applicables aux cotisations sociales (maladie, vieillesse, chômage, allocations, CSG/CRDS, etc.), avec distinction part salariale et patronale.


📂 HTML/

Dossier pour récupérer, versionner et contrôler la page URSSAF source des taux.

check_changement_du_html.py
Récupère l’HTML en ligne, normalise, compare au fichier local, affiche un diff unifié, puis propose de remplacer ou d’enregistrer une copie .remote.html.

recup_html.py
Télécharge la page URSSAF avec en-tête User-Agent, parse avec BeautifulSoup, et enregistre un page.html propre dans ce dossier.

page.html
Snapshot local de référence. Sert de base pour la comparaison et pour un parsing hors-ligne reproductible.

tauxcotisations.html
Extrait représentatif des tableaux URSSAF (patronal/salarial). Utilisé pour aider Gemini à scraper.

📂 scripts/

Automatise la mise à jour des taux depuis l’URSSAF et l’écriture dans config/taux_cotisations.json.

alloc.py
Scrape le taux des allocations familiales (réduit ou plein). Met à jour la part patronale.

FNAL.py
Scrape le FNAL selon l’effectif < 50 ou ≥ 50. Met à jour la part patronale.

MMIDpatronal.py
Scrape le taux maladie employeur (“taux plein à 13 %”). Met à jour securite_sociale_maladie.patronal.

MMIDsalarial.py
Lit isAlsaceMoselle. Scrape le taux maladie salarié Alsace-Moselle si besoin. Met à jour securite_sociale_maladie.salarial.

vieillessepatronal.py
Scrape les taux vieillesse employeur (déplafonné et plafonné). Met à jour retraite_secu_deplafond.patronal et retraite_secu_plafond.patronal.

vieillessesalarial.py
Scrape les taux vieillesse salarié (déplafonné et plafonné). Met à jour retraite_secu_deplafond.salarial et retraite_secu_plafond.salarial.

