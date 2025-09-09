# scripts/PAS/orchestrator.py

import json
import os
import sys
import hashlib
import subprocess
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

# --- CONFIGURATION ---
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DATA_FILE = os.path.join(REPO_ROOT, "data", "pas.json")
LOCK_FILE = os.path.join(REPO_ROOT, "data", ".lock_pas")

SCRIPTS = [
    os.path.join(os.path.dirname(__file__), "PAS.py"),
    os.path.join(os.path.dirname(__file__), "PAS_AI.py"),
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

# --- LOGIQUE DE COMPARAISON ---
def core_signature(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Extrait et normalise la section des données pour la comparaison."""
    sections = payload.get("sections", {})
    # S'assure que les tranches dans chaque zone sont triées pour une comparaison stable
    for zone, tranches in sections.items():
        if isinstance(tranches, list):
            tranches.sort(key=lambda x: (float('inf') if x.get("plafond") is None else x["plafond"]))
    return sections

def _eq_float(a: Optional[float], b: Optional[float], tol: float = 1e-6) -> bool:
    if a is None and b is None: return True
    if a is None or b is None: return a is b
    return abs(float(a) - float(b)) <= tol

def equal_core(sig_a: Dict, sig_b: Dict) -> Tuple[bool, Optional[str]]:
    """Compare deux signatures de données PAS et retourne la localisation de l'erreur."""
    zones = ["metropole", "guadeloupe_reunion_martinique", "guyane_mayotte"]
    for zone in zones:
        if zone not in sig_a or zone not in sig_b:
            return False, f"La zone '{zone}' est manquante dans l'une des sorties."
        
        tranches_a, tranches_b = sig_a[zone], sig_b[zone]
        if len(tranches_a) != len(tranches_b):
            return False, f"Mismatch dans '{zone}': le nombre de tranches diffère ({len(tranches_a)} vs {len(tranches_b)})"

        for i, (tranche_a, tranche_b) in enumerate(zip(tranches_a, tranches_b)):
            if not _eq_float(tranche_a.get("plafond"), tranche_b.get("plafond")):
                return False, f"Mismatch dans '{zone}[{i}].plafond': {tranche_a.get('plafond')} != {tranche_b.get('plafond')}"
            if not _eq_float(tranche_a.get("taux"), tranche_b.get("taux")):
                return False, f"Mismatch dans '{zone}[{i}].taux': {tranche_a.get('taux')} != {tranche_b.get('taux')}"
                
    return True, None

def debug_mismatch(script_a: str, script_b: str, details: str, sig_a: Any, sig_b: Any) -> None:
    """Affiche un message d'erreur clair."""
    print("="*80, file=sys.stderr)
    print("❌ MISMATCH DÉTECTÉ ❌".center(80), file=sys.stderr)
    print("="*80, file=sys.stderr)
    print(f"\nComparaison entre '{script_a}' et '{script_b}'.", file=sys.stderr)
    print(f"📍 {details}\n", file=sys.stderr)

# --- GESTION DU FICHIER DE DONNÉES ---
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
    """Fusionne les sources de métadonnées de tous les scripts."""
    sources = []
    for p in payloads:
        sources.extend(p.get("meta", {}).get("source", []))
    return sources

def update_data_file(zones_data: Dict[str, Any], sources: List[Dict[str, Any]]) -> None:
    """Met à jour le fichier pas.json avec les données validées."""
    print(f"Mise à jour du fichier '{os.path.basename(DATA_FILE)}'...")
    
    # Transformation des données scrapées vers la structure cible
    baremes_list = []
    for zone, tranches in zones_data.items():
        baremes_list.append({
            "periode": "mensuel_2025", # Période déduite du contexte
            "zone": zone,
            "tranches": tranches
        })
    
    # Création du contenu final du fichier
    file_content = {
        "meta": {
            "last_scraped": iso_now(),
            "generator": "scripts/PAS/orchestrator.py",
            "source": sources,
            "hash": hashlib.sha256(json.dumps(baremes_list, sort_keys=True).encode()).hexdigest()
        },
        "baremes": baremes_list # NOTE: clé au pluriel pour contenir plusieurs zones
    }

    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(file_content, f, ensure_ascii=False, indent=2)
    
    print(f"✅ Fichier '{os.path.basename(DATA_FILE)}' mis à jour avec succès.")

# --- SCRIPT PRINCIPAL ---
def main() -> None:
    print("--- Lancement de l'orchestrateur pour le barème PAS ---")
    
    payloads = [run_script(p) for p in SCRIPTS]
    signatures = [core_signature(p) for p in payloads]
    
    are_equal, details = equal_core(signatures[0], signatures[1])
    
    if not are_equal:
        script_a = payloads[0]['__script']
        script_b = payloads[1]['__script']
        debug_mismatch(script_a, script_b, details, signatures[0], signatures[1])
        raise SystemExit("Les scripts ont retourné des valeurs différentes. Mise à jour annulée.")

    print(f"✅ Concordance parfaite entre les sources pour le barème PAS.")
    
    final_data = signatures[0]
    final_sources = merge_sources(payloads)
    
    acquire_lock()
    try:
        update_data_file(final_data, final_sources)
    finally:
        release_lock()

if __name__ == "__main__":
    main()