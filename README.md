# Moteur de Paie en Python

Ce projet est un moteur de calcul de paie en Python, conçu pour générer des bulletins de paie conformes à la législation française. Il est modulaire, piloté par les données, et capable de gérer plusieurs employés et conventions collectives.

## Objectif

L'objectif de ce logiciel est de produire des bulletins de paie PDF précis et justes, en automatisant les calculs complexes liés au salaire brut, aux cotisations sociales, aux réductions de charges, et à l'impôt sur le revenu.

---

## Architecture Générale

Le projet est structuré en quatre parties principales : les données (`data`), le moteur de calcul (`moteur_paie`), la présentation (`templates`), et les scripts (`scripts`).

    .
    ├── data/
    │   ├── employes/
    │   │   └── [NOM_EMPLOYE]/
    │   │       ├── contrat.json
    │   │       ├── horaires_MM.json
    │   │       ├── saisie_du_mois.json
    │   │       └── cumuls.json
    │   │
    │   ├── conventions_collectives.json
    │   ├── cotisations.json
    │   └── ... (autres barèmes légaux)
    │
    ├── moteur_paie/
    │   ├── __init__.py
    │   ├── bulletin.py
    │   ├── calcul_brut.py
    │   ├── calcul_conges.py
    │   ├── calcul_cotisations.py
    │   └── ... (autres modules de calcul)
    │
    ├── scripts/
    │   └── smic/
    │       ├── orchestrator.py
    │       ├── scraper_ia.py
    │       ├── scraper_legisocial.py
    │       └── ...
    │
    ├── templates/
    │   ├── template_bulletin.html
    │   └── style.css
    │
    ├── generateur_fiche_paie.py
    └── requirements.txt

---

## Fonctionnement du Calcul

Le processus de génération d'un bulletin est orchestré par `generateur_fiche_paie.py` et suit un flux logique :

1.  **Configuration** : On choisit l'employé et la période à calculer dans `generateur_fiche_paie.py`.
2.  **Chargement des Données** : `moteur_paie/contexte.py` charge toutes les données pertinentes (contrat, entreprise, barèmes, cumuls, convention collective) dans un objet central.
3.  **Calcul du Brut** : `moteur_paie/calcul_brut.py` calcule le salaire brut en intégrant le salaire de base, les primes, les congés payés, et les heures supplémentaires (avec un décompte hebdomadaire strict).
4.  **Calcul des Cotisations** : `moteur_paie/calcul_cotisations.py` génère toutes les lignes de cotisations sociales (salariales et patronales) en appliquant les taux aux bonnes assiettes. Les réductions (Fillon, etc.) sont également calculées.
5.  **Calcul des Nets** : `moteur_paie/calcul_net.py` calcule la cascade des nets : Net Social, Net Imposable (avec défiscalisation des HS) et le Net à Payer final après impôt et ajustements.
6.  **Assemblage et Rendu** : `moteur_paie/bulletin.py` assemble toutes ces informations dans un dictionnaire final, qui est ensuite passé au template `templates/template_bulletin.html` pour générer le PDF via WeasyPrint.

---

## Installation

1.  Clonez le dépôt.
2.  Créez un environnement virtuel :
    ```shell
    python -m venv venv
    source venv/bin/activate  # Sur macOS/Linux
    venv\Scripts\activate    # Sur Windows
    ```
3.  Installez les dépendances :
    ```shell
    pip install -r requirements.txt
    ```

---

## Utilisation

1.  **Préparez les données** : Assurez-vous que le dossier `data/employes/[NOM_EMPLOYE]/` contient les fichiers `contrat.json`, `horaires_MM.json`, `saisie_du_mois.json` et `cumuls.json` pour l'employé désiré.
2.  **Configurez le calcul** : Ouvrez `generateur_fiche_paie.py` et modifiez les variables en haut de la fonction `generer_une_fiche_de_paie` pour choisir l'employé (`nom_dossier_employe`) et la période (`annee_paie`, `mois_paie`).
3.  **Lancez le script** :
    ```shell
    python generateur_fiche_paie.py
    ```
4.  Le bulletin PDF sera généré dans le dossier de l'employé correspondant.

---

## Le Dossier `scripts/` : Mise à Jour Automatique des Données 🤖

Ce dossier contient des outils pour maintenir les barèmes légaux et conventionnels (SMIC, taux de cotisations, etc.) à jour dans le dossier `data/`.

### Objectif

L'objectif est d'automatiser la collecte des taux et des valeurs depuis des sources externes et de ne mettre à jour les fichiers de données que lorsque l'information est confirmée par plusieurs sources, garantissant ainsi la fiabilité.

### Structure

Chaque sous-dossier (ex: `smic/`, `cotisations/`) correspond à un fichier de données à mettre à jour et contient quatre scripts :

* `scraper_site_A.py`: Un script de scraping ciblé sur une source fiable (ex: le site de l'URSSAF).
* `scraper_site_B.py`: Un second script de scraping sur une autre source (ex: LegiSocial).
* `scraper_ia.py`: Un script plus flexible qui utilise une recherche Google ou une IA pour trouver la valeur sur des sources moins structurées.
* `orchestrator.py`: Le script principal qui pilote les trois autres.

### Principe de Fonctionnement

1.  L'utilisateur lance l'orchestrateur pour une donnée spécifique (ex: `python scripts/smic/orchestrator.py`).
2.  L'`orchestrator.py` exécute les trois scripts de scraping pour récupérer la même information depuis trois sources différentes.
3.  Il compare les trois résultats obtenus.
4.  **Règle de consensus** : Si, et seulement si, **les trois sources retournent une valeur rigoureusement identique**, la donnée est considérée comme fiable et validée.
5.  En cas de consensus, l'orchestrateur met à jour automatiquement le fichier JSON correspondant dans `data/` avec la nouvelle valeur. En cas de divergence, une erreur est levée, nécessitant une vérification manuelle.