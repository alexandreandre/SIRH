# scripts/CFP/orchestrator.py

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
LOCK_FILE = os.path.join(REPO_ROOT, "data", ".lock_cfp")

SCRIPTS = [
    os.path.join(os.path.dirname(__file__), "CFP.py"),
    os.path.join(os.path.dirname(__file__), "CFP_LegiSocial.py"),
    os.path.join(os.path.dirname(__file__), "CFP_AI.py"),
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
    """Extrait et normalise les deux taux CFP pour la comparaison."""
    sections = payload.get("sections", {})
    return {
        "patronal_moins_11": sections.get("patronal_moins_11"),
        "patronal_11_et_plus": sections.get("patronal_11_et_plus"),
    }

def _eq_float(a: Optional[float], b: Optional[float], tol: float = 1e-6) -> bool:
    if a is None or b is None: return a is b
    return abs(float(a) - float(b)) <= tol

def equal_core(a: Dict[str, Any], b: Dict[str, Any]) -> Tuple[bool, str]:
    """Compare deux signatures contenant les deux taux CFP."""
    if not _eq_float(a.get("patronal_moins_11"), b.get("patronal_moins_11")):
        return False, f"Mismatch sur 'patronal_moins_11': {a.get('patronal_moins_11')} != {b.get('patronal_moins_11')}"
    if not _eq_float(a.get("patronal_11_et_plus"), b.get("patronal_11_et_plus")):
        return False, f"Mismatch sur 'patronal_11_et_plus': {a.get('patronal_11_et_plus')} != {b.get('patronal_11_et_plus')}"
    return True, ""

def acquire_lock():
    os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
    try:
        os.open(LOCK_FILE, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        raise SystemExit("Lock présent: écriture en cours.")

def release_lock():
    try:
        os.remove(LOCK_FILE)
    except FileNotFoundError:
        pass

def merge_sources(payloads: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    sources, seen = [], set()
    for p in payloads:
        for s in p.get("meta", {}).get("source", []):
            if s.get("url") and s.get("url") not in seen:
                sources.append(s)
                seen.add(s.get("url"))
    return sources

def update_database(final_rates: Dict[str, Any], sources: List[Dict[str, str]]) -> None:
    """Met à jour l'entrée CFP dans cotisations.json avec les deux taux."""
    print(f"Mise à jour de la cotisation CFP dans '{os.path.basename(DATA_FILE)}'...")
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        db = json.load(f)

    root_key = next((k for k, v in db.items() if isinstance(v, list)), "cotisations")
    
    found = False
    # On utilise l'id 'CFP' comme défini dans ton fichier cotisations.json
    target_id = "CFP" 
    for item in db.get(root_key, []):
        if item.get("id") == target_id:
            item["patronal"] = {
                "taux_moins_11": final_rates["patronal_moins_11"],
                "taux_11_et_plus": final_rates["patronal_11_et_plus"],
            }
            found = True
            break
    
    if not found:
        raise KeyError(f"L'entrée avec id='{target_id}' est introuvable dans cotisations.json")

    db["meta"]["last_scraped"] = iso_now()
    db["meta"]["generator"] = "CFP/orchestrator.py"
    db["meta"]["source"] = sources
    
    data_to_hash = {k: v for k, v in db.items() if k != 'meta'}
    data_to_hash['meta'] = {k: v for k, v in db['meta'].items() if k != 'hash'}
    db["meta"]["hash"] = hashlib.sha256(json.dumps(data_to_hash, sort_keys=True, ensure_ascii=False).encode()).hexdigest()

    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, indent=2)
    print("✅ Fichier mis à jour avec succès.")

def debug_mismatch(script_a, script_b, details):
    print("="*80, file=sys.stderr)
    print("❌ MISMATCH DÉTECTÉ ❌".center(80), file=sys.stderr)
    print("="*80, file=sys.stderr)
    print(f"\nComparaison entre '{script_a}' et '{script_b}'.", file=sys.stderr)
    print(f"📍 {details}\n", file=sys.stderr)

def main() -> None:
    print("--- Lancement de l'orchestrateur pour les taux de CFP ---")
    payloads = [run_script(p) for p in SCRIPTS]
    signatures = [core_signature(p) for p in payloads]

    for i in range(len(signatures) - 1):
        are_equal, details = equal_core(signatures[i], signatures[i+1])
        if not are_equal:
            debug_mismatch(payloads[i]['__script'], payloads[i+1]['__script'], details)
            raise SystemExit("Les scripts ont retourné des valeurs différentes. Mise à jour annulée.")

    print("✅ Concordance parfaite entre toutes les sources pour les taux CFP.")
    
    final_data = signatures[0]
    final_sources = merge_sources(payloads)
    
    acquire_lock()
    try:
        update_database(final_data, final_sources)
    finally:
        release_lock()

if __name__ == "__main__":
    main()