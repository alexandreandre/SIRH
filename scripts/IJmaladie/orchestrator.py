# scripts/IJmaladie/orchestrator.py
import json
import os
import sys
import math
import hashlib
import subprocess
from datetime import datetime, timezone
from typing import Any, Dict, List

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DATA_FILE = os.path.join(REPO_ROOT, "data", "secu.json")
LOCK_FILE = os.path.join(REPO_ROOT, "data", ".lock")

SCRIPTS = [
    os.path.join(os.path.dirname(__file__), "IJmaladie.py"),
    os.path.join(os.path.dirname(__file__), "IJmaladie_LegiSocial.py"),
    os.path.join(os.path.dirname(__file__), "IJmaladie_AI.py"),
]

FIELDS = ["maladie", "maternite_paternite", "at_mp", "at_mp_majoree"]

def iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def run_script(path: str) -> Dict[str, Any]:
    """Exécute un scraper et lit le JSON sur stdout."""
    proc = subprocess.run(
        [sys.executable, path],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        env=os.environ.copy(),
    )
    if proc.returncode != 0:
        print(f"\n[ERREUR] {os.path.basename(path)} a échoué (code {proc.returncode})", file=sys.stderr)
        if proc.stdout.strip():
            print("[stdout]", proc.stdout, file=sys.stderr)
        if proc.stderr.strip():
            print("[stderr]", proc.stderr, file=sys.stderr)
        raise SystemExit(2)

    out = proc.stdout.strip()
    try:
        payload = json.loads(out)
        payload.setdefault("meta", {}).setdefault("generator", os.path.basename(path))
        payload["__script"] = os.path.basename(path)
        return payload
    except Exception as e:
        print(
            f"[ERREUR] Sortie non-JSON depuis {os.path.basename(path)}: {e}\n---stdout---\n{out}\n-------------",
            file=sys.stderr,
        )
        raise SystemExit(2)

def core_signature(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Noyau comparable: seules les 4 valeurs numériques nous intéressent."""
    if payload.get("id") != "ij_maladie":
        raise SystemExit("id attendu 'ij_maladie'")
    vals = payload.get("valeurs", {}) or {}
    core_vals = {}
    for k in FIELDS:
        v = vals.get(k, None)
        core_vals[k] = None if v is None else round(float(v), 2)
    return {"valeurs": core_vals}

def equal_core(a: Dict[str, Any], b: Dict[str, Any], abs_tol: float = 0.01) -> bool:
    for k in FIELDS:
        va, vb = a["valeurs"].get(k), b["valeurs"].get(k)
        if va is None or vb is None:
            if va is not vb:
                return False
        else:
            if not math.isclose(float(va), float(vb), rel_tol=0.0, abs_tol=abs_tol):
                return False
    return True

def acquire_lock() -> None:
    os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
    try:
        fd = os.open(LOCK_FILE, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.write(fd, b"lock")
        os.close(fd)
    except FileExistsError:
        raise SystemExit("Lock présent: écriture en cours.")

def release_lock() -> None:
    try:
        os.remove(LOCK_FILE)
    except FileNotFoundError:
        pass

def compute_hash(obj: Any) -> str:
    return hashlib.sha256(json.dumps(obj, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()

def merge_sources(payloads: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    seen, out = set(), []
    for p in payloads:
        for s in p.get("meta", {}).get("source", []):
            key = (s.get("url", ""), s.get("label", ""))
            if key not in seen:
                seen.add(key)
                out.append({"url": s.get("url", ""), "label": s.get("label", ""), "date_doc": s.get("date_doc", "")})
    return out

def load_or_init_db() -> Dict[str, Any]:
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    # squelette neuf
    return {
        "meta": {"last_scraped": "", "hash": "", "source": [], "generator": ""},
        "plafonds_indemnites_journalieres": {
            "maladie": 0,
            "maternite_paternite": 0,
            "at_mp": 0,
            "at_mp_majoree": 0,
        },
        "pmss": {
            "annuel": 0,
            "trimestriel": 0,
            "mensuel": 0,
            "quinzaine": 0,
            "hebdomadaire": 0,
            "journalier": 0,
            "horaire": 0,
        },
    }

def update_database(final_core: Dict[str, Any], sources: List[Dict[str, str]]) -> None:
    db = load_or_init_db()

    # upsert des 4 champs uniquement (pas de 'unite' ici)
    section = db.setdefault("plafonds_indemnites_journalieres", {})
    for k in FIELDS:
        section[k] = final_core["valeurs"].get(k)

    db["meta"]["last_scraped"] = iso_now()
    db["meta"]["generator"] = "IJmaladie/orchestrator.py"
    db["meta"]["source"] = sources
    db["meta"]["hash"] = compute_hash(db.get("plafonds_indemnites_journalieres", {}))

    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, indent=2)

def debug_mismatch(payloads: List[Dict[str, Any]], sigs: List[Dict[str, Any]]) -> None:
    print("MISMATCH entre les sources:", file=sys.stderr)
    for k in FIELDS:
        line = " | ".join(f"{p.get('__script','?')}={s['valeurs'].get(k)}" for p, s in zip(payloads, sigs))
        print(f"  ► {k}: {line}", file=sys.stderr)
    for p, s in zip(payloads, sigs):
        script = p.get("__script", "?")
        srcs = p.get("meta", {}).get("source", [])
        src = srcs[0]["url"] if srcs else ""
        print(f"- {script} -> source={src} | core={json.dumps(s, ensure_ascii=False)}", file=sys.stderr)

def debug_success(payloads: List[Dict[str, Any]], sigs: List[Dict[str, Any]]) -> None:
    joined = " | ".join(
        f"{p.get('__script','?')}: "
        f"maladie={s['valeurs']['maladie']}, "
        f"maternite_paternite={s['valeurs']['maternite_paternite']}, "
        f"at_mp={s['valeurs']['at_mp']}, "
        f"at_mp_majoree={s['valeurs']['at_mp_majoree']}"
        for p, s in zip(payloads, sigs)
    )
    print(f"OK: concordance IJ plafonds => {joined}")

def main() -> None:
    payloads = [run_script(p) for p in SCRIPTS]
    sigs = [core_signature(p) for p in payloads]

    # concordance stricte champ par champ à 0,01 €
    if not (equal_core(sigs[0], sigs[1]) and equal_core(sigs[1], sigs[2])):
        debug_mismatch(payloads, sigs)
        raise SystemExit(2)

    debug_success(payloads, sigs)

    acquire_lock()
    try:
        update_database(sigs[0], merge_sources(payloads))
        print("OK: base secu mise à jour (IJ plafonds).")
    finally:
        release_lock()

if __name__ == "__main__":
    main()
