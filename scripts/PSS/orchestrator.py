# scripts/PSS/orchestrator.py

import json
import os
import sys
import hashlib
import subprocess
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

# --- CONFIGURATION ---
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DATA_FILE = os.path.join(REPO_ROOT, "data", "secu.json")
LOCK_FILE = os.path.join(REPO_ROOT, "data", ".lock_pss")

SCRIPTS = [
    os.path.join(os.path.dirname(__file__), "PSS.py"),
    os.path.join(os.path.dirname(__file__), "PSS_LegiSocial.py"),
    os.path.join(os.path.dirname(__file__), "PSS_AI.py"),
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

def equal_core(sig_a: Dict, sig_b: Dict) -> Tuple[bool, Optional[str]]:
    """
    Compare deux dictionnaires de plafonds sur leurs clés communes.
    """
    keys_a = set(sig_a.keys())
    keys_b = set(sig_b.keys())
    
    # On ne compare que les clés présentes dans les DEUX dictionnaires
    common_keys = keys_a.intersection(keys_b)
    
    # On s'assure qu'un minimum de clés vitales sont bien présentes
    essential_keys = {"annuel", "mensuel", "journalier"}
    if not essential_keys.issubset(common_keys):
        missing = essential_keys - common_keys
        return False, f"Une ou plusieurs clés PSS essentielles sont manquantes : {missing}"

    print(f"  - Comparaison sur {len(common_keys)} clés communes...", file=sys.stderr)

    for key in sorted(list(common_keys)):
        val_a = sig_a.get(key)
        val_b = sig_b.get(key)
        
        if val_a != val_b:
            return False, f"Mismatch sur la clé commune '{key}': {val_a} != {val_b}"
            
    return True, None

def debug_mismatch(script_a: str, script_b: str, details: str) -> None:
    """Affiche un message d'erreur clair en cas de différence."""
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
    """Fusionne les métadonnées de source de tous les scripts."""
    sources = []
    seen_urls = set()
    for p in payloads:
        for source in p.get("meta", {}).get("source", []):
            if source.get("url") not in seen_urls:
                sources.append(source)
                seen_urls.add(source.get("url"))
    return sources

def update_data_file(plafonds_data: Dict[str, Any], sources: List[Dict[str, Any]]) -> None:
    """Met à jour le fichier cotisations.json avec les plafonds validés."""
    print(f"Mise à jour du fichier '{os.path.basename(DATA_FILE)}'...")
    
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

        if "pss" not in data:
            raise KeyError("La clé 'pss' est manquante dans le fichier JSON cible.")

        # On s'assure de ne mettre à jour que les clés du dictionnaire final
        # pour ne pas ajouter de clés manquantes (ex: 'quinzaine') si elles n'existent pas déjà
        final_pss_data = data["pss"].copy()
        updated_keys = 0
        for key, value in plafonds_data.items():
            if key in final_pss_data and final_pss_data[key] != value:
                final_pss_data[key] = value
                updated_keys += 1
            elif key not in final_pss_data:
                final_pss_data[key] = value # Ajoute la clé si elle n'existait pas du tout
                updated_keys += 1

        if updated_keys == 0:
            print("  - Les valeurs PSS sont déjà à jour. Aucune modification nécessaire.")
            return

        print(f"  - Mise à jour de {updated_keys} valeur(s) PSS...")
        data["pss"] = final_pss_data
        
        data["meta"]["last_scraped"] = iso_now()
        data["meta"]["generator"] = "scripts/PSS/orchestrator.py"
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
    print("--- Lancement de l'orchestrateur pour les Plafonds de la Sécurité Sociale (PSS) ---")
    
    payloads = [run_script(p) for p in SCRIPTS]
    signatures = [core_signature(p) for p in payloads]
    
    # La comparaison se fait toujours par rapport à la source primaire (index 0)
    primary_sig = signatures[0]
    
    for i in range(1, len(signatures)):
        are_equal, details = equal_core(primary_sig, signatures[i])
        if not are_equal:
            script_a = payloads[0]['__script']
            script_b = payloads[i]['__script']
            debug_mismatch(script_a, script_b, details)
            raise SystemExit("Les scripts ont retourné des valeurs différentes. Mise à jour annulée.")

    print("✅ Concordance parfaite entre les sources sur les clés communes.")
    
    # Les données finales sont celles de la source primaire, qui est la plus complète
    final_data = primary_sig
    final_sources = merge_sources(payloads)
    
    acquire_lock()
    try:
        update_data_file(final_data, final_sources)
    finally:
        release_lock()

if __name__ == "__main__":
    main()