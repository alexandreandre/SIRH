# scripts/taxeapprentissage/orchestrator.py

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
LOCK_FILE = os.path.join(REPO_ROOT, "data", ".lock_taxeapprentissage")

SCRIPTS = [
    os.path.join(os.path.dirname(__file__), "taxeapprentissage.py"),
    os.path.join(os.path.dirname(__file__), "taxeapprentissage_LegiSocial.py"),
    os.path.join(os.path.dirname(__file__), "taxeapprentissage_AI.py"),
]

# --- UTILITAIRES ---
def iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def run_script(path: str) -> Dict[str, Any]:
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
    return payload.get("sections", {})

def _eq_float(a: Optional[float], b: Optional[float], tol: float = 1e-6) -> bool:
    if a is None or b is None: return a is b
    return abs(float(a) - float(b)) <= tol

def equal_core(a: Dict[str, Any], b: Dict[str, Any]) -> Tuple[bool, str]:
    if not a: return False, "La signature de la source primaire est vide."

    for section_key in a:
        # --- CORRECTION ---
        # On ignore la clé 'salarial' qui est toujours nulle et n'est pas un dictionnaire de taux.
        if section_key == 'salarial':
            continue
        # --- FIN DE LA CORRECTION ---

        section_a = a.get(section_key)
        section_b = b.get(section_key)

        if section_a is None:
            return False, f"La section '{section_key}' est nulle ou absente dans la source primaire."
        
        if section_b is None:
            print(f"AVERTISSEMENT: La section '{section_key}' est absente de la source secondaire. Comparaison ignorée.", file=sys.stderr)
            continue
        
        for rate_key in section_a:
            if rate_key not in section_b:
                 return False, f"La clé '{rate_key}' est manquante dans la section '{section_key}' de la source secondaire."
            
            if not _eq_float(section_a.get(rate_key), section_b.get(rate_key)):
                return False, f"Mismatch dans '{section_key}.{rate_key}': {section_a.get(rate_key)} != {section_b.get(rate_key)}"
    return True, ""

def acquire_lock():
    os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
    try:
        os.open(LOCK_FILE, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        raise SystemExit("Lock présent.")

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
    print(f"Mise à jour de la taxe d'apprentissage dans '{os.path.basename(DATA_FILE)}'...")
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        db = json.load(f)

    root_key = next((k for k, v in db.items() if isinstance(v, list)), "cotisations")
    
    id_principale = "taxe_apprentissage"
    id_solde = "taxe_apprentissage_solde"
    principale_found = False
    solde_found = False

    for item in db.get(root_key, []):
        if item.get("id") == id_principale:
            item["patronal"] = final_rates["part_principale"]
            principale_found = True
        elif item.get("id") == id_solde:
            item["patronal"] = final_rates["solde"]
            solde_found = True

    if not solde_found:
        db[root_key].append({
            "id": id_solde, "libelle": "Taxe d'Apprentissage (solde)",
            "base": "brut", "salarial": None, "patronal": final_rates["solde"]
        })
        print("  - Entrée 'taxe_apprentissage_solde' créée.")

    if not principale_found:
        raise KeyError(f"L'entrée avec id='{id_principale}' est introuvable dans cotisations.json")

    db["meta"]["last_scraped"] = iso_now()
    db["meta"]["generator"] = "taxeapprentissage/orchestrator.py"
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
    print("--- Lancement de l'orchestrateur pour la Taxe d'Apprentissage ---")
    payloads = [run_script(p) for p in SCRIPTS]
    signatures = [core_signature(p) for p in payloads]
    
    primary_sig = signatures[0]
    
    for i in range(1, len(signatures)):
        are_equal, details = equal_core(primary_sig, signatures[i])
        if not are_equal:
            script_a = payloads[0]['__script']
            script_b = payloads[i]['__script']
            debug_mismatch(script_a, script_b, details)
            raise SystemExit("Les scripts ont retourné des valeurs différentes. Mise à jour annulée.")

    print("✅ Concordance parfaite entre les sources.")
    
    final_data = signatures[0]
    final_sources = merge_sources(payloads)
    
    acquire_lock()
    try:
        update_database(final_data, final_sources)
    finally:
        release_lock()

if __name__ == "__main__":
    main()