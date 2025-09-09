# moteur_paie/contexte.py

import json
import sys
from pathlib import Path
from typing import Any, Dict, List

class ContextePaie:
    def __init__(self, chemin_contrat: str, chemin_entreprise: str, chemin_cumuls: str, chemin_data_dir: str = 'data'):
        """
        Initialise le contexte en chargeant tous les fichiers JSON.
        
        Args:
            chemin_contrat (str): Chemin vers le fichier contrat.json du salarié.
            chemin_entreprise (str): Chemin vers le fichier entreprise.json.
            chemin_cumuls (str): Chemin vers le fichier cumuls.json du salarié.
            chemin_data_dir (str): Chemin vers le dossier contenant les barèmes.
        """
        print("INFO: Initialisation du contexte de paie...", file=sys.stderr)
        data_dir = Path(chemin_data_dir)

        self.entreprise = self._load_json(chemin_entreprise).get('entreprise', {})
        self.contrat = self._load_json(chemin_contrat)
        
        # CORRIGÉ: On charge le fichier de cumuls spécifique à l'employé
        self.cumuls = self._load_json(chemin_cumuls)
        
        self.baremes = {
            "cotisations": self._load_json(data_dir / 'cotisations.json'),
            "heures_supp": self._load_json(data_dir / 'heuresupp.json'),
            "pas": self._load_json(data_dir / 'pas.json').get('baremes', []),
            "smic": self._load_json(data_dir / 'smic.json').get('smic_horaire', {}),
            "pss": self._load_json(data_dir / 'plafonds.json').get('pss', {}),
            "frais_pro": self._load_json(data_dir / 'frais_pro.json'),
            "primes": self._load_json(data_dir / 'primes.json').get('primes', []),
            "conventions_collectives": self._load_json(data_dir / 'conventions_collectives.json')
        }
        print("INFO: Contexte chargé avec succès.", file=sys.stderr)

    def _load_json(self, file_path: Path | str) -> Dict[str, Any]:
        """Fonction utilitaire pour charger un fichier JSON en gérant les erreurs."""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except FileNotFoundError:
            raise FileNotFoundError(f"Erreur critique : Le fichier de données '{file_path}' est introuvable.")
        except json.JSONDecodeError as e:
            raise json.JSONDecodeError(f"Erreur critique : Le fichier JSON '{file_path}' est mal formaté. Détails: {e}")

    # --- Propriétés d'accès rapide (Données "statiques") ---
    
    @property
    def effectif(self) -> int:
        """Retourne l'effectif de l'entreprise."""
        return self.entreprise.get('parametres_paie', {}).get('effectif', 0)

    @property
    def statut_salarie(self) -> str:
        """Retourne le statut du salarié ('Cadre' ou 'Non-Cadre')."""
        return self.contrat.get('contrat', {}).get('statut', 'Non-Cadre')

    @property
    def salaire_base_mensuel(self) -> float:
        """Retourne le salaire de base brut mensuel."""
        return self.contrat.get('remuneration', {}).get('salaire_de_base', {}).get('valeur', 0.0)

    @property
    def duree_hebdo_contrat(self) -> float:
        """Retourne la durée hebdomadaire de travail du contrat."""
        return self.contrat.get('contrat', {}).get('temps_travail', {}).get('duree_hebdomadaire', 35)

    @property
    def is_alsace_moselle(self) -> bool:
        """Indique si le salarié dépend du régime Alsace-Moselle."""
        return self.contrat.get('specificites_paie', {}).get('is_alsace_moselle', False)

    # --- Propriétés d'accès rapide (Données "variables" du mois) ---

    @property
    def saisie_du_mois(self) -> dict:
        """Retourne le dictionnaire des variables mensuelles."""
        return self.contrat.get('saisie_du_mois', {})

    @property
    def heures_sup_du_mois(self) -> float:
        """Retourne les heures supplémentaires conjoncturelles du mois."""
        return self.saisie_du_mois.get('heures_supplementaires_conjoncturelles', 0.0)

    @property
    def heures_absence_du_mois(self) -> float:
        """Retourne les heures d'absence non maintenues du mois."""
        return self.saisie_du_mois.get('heures_absence_non_maintenues', 0.0)
    
    @property
    def primes_du_mois(self) -> dict:
        """Retourne les primes exceptionnelles du mois."""
        return self.saisie_du_mois.get('primes_saisies', {})
    

    @property
    def cumuls_annee_precedente(self) -> dict:
        """Retourne le dictionnaire des cumuls arrêtés à la fin du mois précédent."""
        return self.cumuls.get('cumuls', {})

    # --- Fonctions utilitaires ---

    def get_cotisation_by_id(self, coti_id: str) -> Dict[str, Any] | None:
        """Récupère une ligne de cotisation par son ID depuis cotisations.json."""
        root_key = next((k for k, v in self.baremes['cotisations'].items() if isinstance(v, list)), None)
        if not root_key:
            return None
            
        for coti in self.baremes['cotisations'].get(root_key, []):
            if coti.get('id') == coti_id:
                return coti
        return None