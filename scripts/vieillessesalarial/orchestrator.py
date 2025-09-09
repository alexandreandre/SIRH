# scripts/vieillessesalarial/orchestrator.py

import json
import os
import sys
import hashlib
import subprocess
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

# --- CONFIGURATION ---
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DATA_FILE = os.path.join(REPO_ROOT, "data", "cotisations.json")
LOCK_FILE = os.path.join(REPO_ROOT, "data", ".lock_vieillesse_salarial")

SCRIPTS = [
    os.path.join(os.path.dirname(__file__), "vieillessesalarial.py"),
    os.path.join(os.path.dirname(__file__), "vieillessesalarial_LegiSocial.py"),
    os.path.join(os.path.dirname(__file__), "vieillessesalarial_AI.py"),
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
def core_signature(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Extrait la section des données pour la comparaison."""
    return payload.get("sections", {})

def _eq_float(a: Optional[float], b: Optional[float], tol: float = 1e-6) -> bool:
    if a is None or b is None: return False
    return abs(float(a) - float(b)) <= tol

def equal_core(sig_a: Dict, sig_b: Dict) -> Tuple[bool, Optional[str]]:
    """Compare deux dictionnaires de taux."""
    keys_to_check = ["deplafonne", "plafonne"]
    for key in keys_to_check:
        if key not in sig_a or key not in sig_b:
            return False, f"La clé '{key}' est manquante dans l'une des sorties."
        
        val_a = sig_a.get(key)
        val_b = sig_b.get(key)
        
        if not _eq_float(val_a, val_b):
            return False, f"Mismatch sur la clé '{key}': {val_a} != {val_b}"
            
    return True, None

def debug_mismatch(script_a: str, script_b: str, details: str) -> None:
    print("="*80, file=sys.stderr)
    print("❌ MISMATCH DÉTECTÉ ❌".center(80), file=sys.stderr)
    print("="*80, file=sys.stderr)
    print(f"\nComparaison entre '{script_a}' et '{script_b}'.", file=sys.stderr)
    print(f"📍 {details}\n", file=sys.stderr)

def acquire_lock():
    os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
    try:
        os.open(LOCK_FILE, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        raise SystemExit("Un autre processus est déjà en cours d'écriture (lock présent).")

def release_lock():
    try:
        os.remove(LOCK_FILE)
    except FileNotFoundError:
        pass
        
def merge_sources(payloads: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    sources, seen_urls = [], set()
    for p in payloads:
        for source in p.get("meta", {}).get("source", []):
            if source.get("url") not in seen_urls:
                sources.append(source)
                seen_urls.add(source.get("url"))
    return sources

def update_data_file(taux_data: Dict[str, Any], sources: List[Dict[str, Any]]) -> None:
    """Met à jour le fichier cotisations.json avec les taux salariaux validés."""
    print(f"Mise à jour du fichier '{os.path.basename(DATA_FILE)}'...")
    
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

        plafond_updated = False
        deplafond_updated = False
        
        root_key = next((k for k, v in data.items() if isinstance(v, list)), None)
        if not root_key:
             raise KeyError("Impossible de trouver la liste principale des cotisations dans le fichier JSON.")

        for item in data[root_key]:
            item_id = item.get("id")
            if item_id == "retraite_secu_plafond":
                item["salarial"] = taux_data["plafonne"]
                plafond_updated = True
            elif item_id == "retraite_secu_deplafond":
                item["salarial"] = taux_data["deplafonne"]
                deplafond_updated = True

        if not (plafond_updated and deplafond_updated):
             raise KeyError("Impossible de trouver les objets avec id 'retraite_secu_plafond' et/ou 'retraite_secu_deplafond'.")

        print("  - Taux salariaux plafonné et déplafonné mis à jour.")
        data["meta"]["last_scraped"] = iso_now()
        data["meta"]["generator"] = "scripts/vieillessesalarial/orchestrator.py"
        data["meta"]["source"] = sources
        
        data_to_hash = {k: v for k, v in data.items() if k != 'meta'}
        data_to_hash['meta'] = {k: v for k, v in data['meta'].items() if k != 'hash'}
        new_hash = hashlib.sha256(json.dumps(data_to_hash, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        data["meta"]["hash"] = new_hash
        
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        print(f"✅ Fichier '{os.path.basename(DATA_FILE)}' mis à jour avec succès.")
        
    except FileNotFoundError:
        print(f"ERREUR : Le fichier de données '{DATA_FILE}' est introuvable.", file=sys.stderr)
        raise
    except Exception as e:
        print(f"ERREUR lors de la mise à jour du fichier de données : {e}", file=sys.stderr)
        raise

# --- SCRIPT PRINCIPAL ---
def main() -> None:
    print("--- Lancement de l'orchestrateur pour les taux de vieillesse salariaux ---")
    
    payloads = [run_script(p) for p in SCRIPTS]
    signatures = [core_signature(p) for p in payloads]
    
    for i in range(len(signatures) - 1):
        are_equal, details = equal_core(signatures[i], signatures[i+1])
        if not are_equal:
            script_a = payloads[i]['__script']
            script_b = payloads[i+1]['__script']
            debug_mismatch(script_a, script_b, details)
            raise SystemExit("Les scripts ont retourné des valeurs différentes. Mise à jour annulée.")

    print("✅ Concordance parfaite entre toutes les sources.")
    
    final_data = signatures[0]
    final_sources = merge_sources(payloads)
    
    acquire_lock()
    try:
        update_data_file(final_data, final_sources)
    finally:
        release_lock()

if __name__ == "__main__":
    main()