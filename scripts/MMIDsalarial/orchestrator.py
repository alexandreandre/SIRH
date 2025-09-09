# scripts/MMIDsalarial/orchestrator.py

import json
import os
import sys
import subprocess
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

# --- CONFIGURATION ---
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DATA_FILE = os.path.join(REPO_ROOT, "data", "cotisations.json") # Le fichier à mettre à jour
LOCK_FILE = os.path.join(REPO_ROOT, "data", ".lock")

SCRIPTS = [
    os.path.join(os.path.dirname(__file__), "MMIDsalarial.py"),
    os.path.join(os.path.dirname(__file__), "MMIDsalarial_LegiSocial.py"),
    os.path.join(os.path.dirname(__file__), "MMIDsalarial_AI.py"),
]

# --- UTILITAIRES ---
def iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def run_script(path: str) -> Dict[str, Any]:
    """Exécute un script et retourne sa sortie JSON."""
    proc = subprocess.run(
        [sys.executable, path],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        env=os.environ.copy(),
    )
    if proc.returncode != 0:
        print(f"\n[ERREUR] {os.path.basename(path)} a échoué (code {proc.returncode})", file=sys.stderr)
        if proc.stderr.strip():
            print(f"--- stderr de {os.path.basename(path)} ---\n{proc.stderr.strip()}", file=sys.stderr)
        raise SystemExit(f"Échec du script {os.path.basename(path)}")

    try:
        payload = json.loads(proc.stdout.strip())
        payload["__script"] = os.path.basename(path)
        return payload
    except Exception as e:
        print(f"[ERREUR] Sortie non-JSON depuis {os.path.basename(path)}: {e}", file=sys.stderr)
        raise SystemExit(2)

# --- LOGIQUE DE L'ORCHESTRATEUR ---
def core_signature(payload: Dict[str, Any]) -> Optional[float]:
    """Extrait la valeur clé (le taux) du JSON d'un script."""
    try:
        return float(payload["sections"]["alsace_moselle"]["taux_salarial"])
    except (KeyError, TypeError, ValueError):
        return None

def _eq_float(a: Optional[float], b: Optional[float], tol: float = 1e-6) -> bool:
    """Compare deux floats avec une tolérance."""
    if a is None or b is None: return False
    return abs(a - b) <= tol

def debug_mismatch(script_a: str, script_b: str, sig_a: Any, sig_b: Any) -> None:
    """Affiche un message d'erreur clair en cas de différence."""
    print("="*80, file=sys.stderr)
    print("❌ MISMATCH DÉTECTÉ ❌".center(80), file=sys.stderr)
    print("="*80, file=sys.stderr)
    print(f"\nLes valeurs extraites par les scripts ne sont pas identiques :\n", file=sys.stderr)
    print(f"  - Script A ({script_a}): {sig_a}", file=sys.stderr)
    print(f"  - Script B ({script_b}): {sig_b}", file=sys.stderr)
    print("\n" + "="*80, file=sys.stderr)

def acquire_lock() -> None:
    """Pose un verrou pour éviter les exécutions concurrentes."""
    os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
    try:
        fd = os.open(LOCK_FILE, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.close(fd)
    except FileExistsError:
        raise SystemExit("Un autre processus est déjà en cours d'écriture (lock présent).")

def release_lock() -> None:
    """Lève le verrou."""
    try:
        os.remove(LOCK_FILE)
    except FileNotFoundError:
        pass

def update_data_file(taux: float) -> None:
    """Met à jour le fichier de données avec le taux validé."""
    try:
        print(f"Mise à jour du fichier '{os.path.basename(DATA_FILE)}'...")
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

        # Cherche la bonne section à mettre à jour
        target_found = False
        # Hypothèse: le JSON contient une clé racine (ex: "TAUX_COTISATIONS") qui contient une liste
        for key, value in data.items():
            if isinstance(value, list):
                for item in value:
                    if isinstance(item, dict) and item.get("id") == "securite_sociale_maladie":
                        print(f"  - Cible trouvée : 'id: securite_sociale_maladie'.")
                        current_value = item.get("salarial_Alsace_Moselle")
                        if current_value == taux:
                            print("  - La valeur est déjà à jour. Aucune modification nécessaire.")
                            return
                        
                        item["salarial_Alsace_Moselle"] = taux
                        print(f"  - Mise à jour de 'salarial_Alsace_Moselle': {current_value} -> {taux}")
                        target_found = True
                        break
            if target_found:
                break
        
        if not target_found:
             raise KeyError("Impossible de trouver l'objet avec `id: securite_sociale_maladie` dans le fichier JSON.")

        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        print(f"✅ Fichier mis à jour avec succès.")

    except FileNotFoundError:
        print(f"ERREUR : Le fichier de données '{DATA_FILE}' est introuvable.", file=sys.stderr)
        raise
    except Exception as e:
        print(f"ERREUR lors de la mise à jour du fichier de données : {e}", file=sys.stderr)
        raise

# --- SCRIPT PRINCIPAL ---
def main() -> None:
    """Exécute les scripts, compare leurs résultats et met à jour le fichier de données."""
    print("--- Lancement de l'orchestrateur pour le taux maladie Alsace-Moselle ---")
    
    payloads = [run_script(p) for p in SCRIPTS]
    signatures = [core_signature(p) for p in payloads]
    
    # Vérification de la concordance
    is_ok = True
    for i in range(len(signatures) - 1):
        if not _eq_float(signatures[i], signatures[i+1]):
            script_a = payloads[i]['__script']
            script_b = payloads[i+1]['__script']
            debug_mismatch(script_a, script_b, signatures[i], signatures[i+1])
            is_ok = False
            break
            
    if not is_ok:
        raise SystemExit("Les scripts ont retourné des valeurs différentes. Mise à jour annulée.")

    final_taux = signatures[0]
    print(f"✅ Concordance parfaite entre les sources. Taux validé : {final_taux}")
    
    acquire_lock()
    try:
        update_data_file(final_taux)
    finally:
        release_lock()

if __name__ == "__main__":
    main()