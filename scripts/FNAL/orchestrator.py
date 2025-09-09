# scripts/FNAL/orchestrator.py
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
LOCK_FILE = os.path.join(REPO_ROOT, "data", ".lock_fnal")

SCRIPTS = [
    os.path.join(os.path.dirname(__file__), "FNAL.py"),
    os.path.join(os.path.dirname(__file__), "FNAL_AI.py"),         
    os.path.join(os.path.dirname(__file__), "FNAL_LegiSocial.py"),
]

# --- UTILITAIRES ---
def iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def run_script(path: str) -> Dict[str, Any]:
    """Exécute un script et récupère son payload JSON (stdout)."""
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
        raise SystemExit(2)

    try:
        payload = json.loads(proc.stdout.strip())
        payload["__script"] = os.path.basename(path)
        return payload
    except Exception as e:
        print(f"[ERREUR] Sortie non-JSON depuis {os.path.basename(path)}: {e}", file=sys.stderr)
        raise SystemExit(2)

# --- LOGIQUE DE L'ORCHESTRATEUR ---
def core_signature(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Extrait et normalise les deux taux FNAL pour la comparaison."""
    sections = payload.get("sections", {})
    return {
        "patronal_moins_50": sections.get("patronal_moins_50"),
        "patronal_50_et_plus": sections.get("patronal_50_et_plus"),
    }

def _eq_float(a: Optional[float], b: Optional[float], tol: float = 1e-6) -> bool:
    if a is None or b is None: return a is b
    return abs(float(a) - float(b)) <= tol

def equal_core(a: Dict[str, Any], b: Dict[str, Any]) -> Tuple[bool, str]:
    """Compare deux signatures contenant les deux taux FNAL."""
    if not _eq_float(a.get("patronal_moins_50"), b.get("patronal_moins_50")):
        return False, f"Mismatch sur 'patronal_moins_50': {a.get('patronal_moins_50')} != {b.get('patronal_moins_50')}"
    if not _eq_float(a.get("patronal_50_et_plus"), b.get("patronal_50_et_plus")):
        return False, f"Mismatch sur 'patronal_50_et_plus': {a.get('patronal_50_et_plus')} != {b.get('patronal_50_et_plus')}"
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
    """Met à jour l'entrée FNAL dans cotisations.json avec les deux taux."""
    print(f"Mise à jour de la cotisation FNAL dans '{os.path.basename(DATA_FILE)}'...")
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        db = json.load(f)

    root_key = next((k for k, v in db.items() if isinstance(v, list)), "cotisations")
    
    found = False
    for item in db.get(root_key, []):
        if item.get("id") == "fnal":
            # La clé "patronal" contient maintenant un objet avec les deux taux
            item["patronal"] = {
                "taux_moins_50": final_rates["patronal_moins_50"],
                "taux_50_et_plus": final_rates["patronal_50_et_plus"],
            }
            found = True
            break
    
    if not found:
        raise KeyError("L'entrée avec id='fnal' est introuvable dans cotisations.json")

    # Mise à jour des métadonnées et du hash global
    db["meta"]["last_scraped"] = iso_now()
    db["meta"]["generator"] = "FNAL/orchestrator.py"
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
    print("--- Lancement de l'orchestrateur pour les taux FNAL ---")
    payloads = [run_script(p) for p in SCRIPTS]
    signatures = [core_signature(p) for p in payloads]

    # Comparaison séquentielle : chaque script est comparé au précédent
    for i in range(len(signatures) - 1):
        are_equal, details = equal_core(signatures[i], signatures[i+1])
        if not are_equal:
            debug_mismatch(payloads[i]['__script'], payloads[i+1]['__script'], details)
            raise SystemExit("Les scripts ont retourné des valeurs différentes. Mise à jour annulée.")

    print("✅ Concordance parfaite entre toutes les sources pour les taux FNAL.")
    
    final_data = signatures[0] # On prend les données du premier script comme référence
    final_sources = merge_sources(payloads)
    
    acquire_lock()
    try:
        update_database(final_data, final_sources)
    finally:
        release_lock()

if __name__ == "__main__":
    main()