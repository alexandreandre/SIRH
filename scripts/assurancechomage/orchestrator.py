# scripts/assurancechomage/orchestrator.py

import json
import os
import sys
import hashlib
import subprocess
from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple

# --- Paths ---
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DATA_FILE = os.path.join(REPO_ROOT, "data", "cotisations.json")
LOCK_FILE = os.path.join(REPO_ROOT, "data", ".lock")

SCRIPTS: List[Tuple[str, str]] = [
    ("assurancechomage.py",       os.path.join(os.path.dirname(__file__), "assurancechomage.py")),
    ("assurancechomage_AI.py",    os.path.join(os.path.dirname(__file__), "assurancechomage_AI.py")),
    ("assurancechomage_LegiSocial.py", os.path.join(os.path.dirname(__file__), "assurancechomage_LegiSocial.py")),
]

# --- Helpers ---
def iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def run_script(label: str, path: str) -> Dict[str, Any]:
    """Run a scraper and return its JSON payload (printed on stdout)."""
    proc = subprocess.run(
        [sys.executable, path],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,  # ensure relative paths inside scripts work
        env=os.environ.copy(),
    )
    if proc.returncode != 0:
        print(f"\n[ERREUR] {label} a échoué (code {proc.returncode})", file=sys.stderr)
        if proc.stdout.strip():
            print("[stdout]", proc.stdout, file=sys.stderr)
        if proc.stderr.strip():
            print("[stderr]", proc.stderr, file=sys.stderr)
        raise SystemExit(2)
    out = proc.stdout.strip()
    try:
        payload = json.loads(out)
        payload["__script"] = label  # tag for debug
        return payload
    except Exception as e:
        print(
            f"[ERREUR] Sortie non-JSON depuis {label}: {e}\n---stdout---\n{out}\n-------------",
            file=sys.stderr,
        )
        raise SystemExit(2)

def core_signature(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize payload to the comparable core for Assurance chômage."""
    if payload.get("id") != "assurance_chomage":
        raise SystemExit("id attendu 'assurance_chomage'")
    patro = payload.get("valeurs", {}).get("patronal", None)
    patro = None if patro is None else round(float(patro), 6)
    return {
        "id": payload.get("id"),
        "type": payload.get("type"),
        "libelle": payload.get("libelle"),
        "base": payload.get("base"),
        "valeurs": {"salarial": None, "patronal": patro},
    }

def equal_core(a: Dict[str, Any], b: Dict[str, Any], tol: float = 1e-9) -> bool:
    for k in ("id", "type", "libelle", "base"):
        if a.get(k) != b.get(k):
            return False
    pa, pb = a["valeurs"]["patronal"], b["valeurs"]["patronal"]
    if pa is None or pb is None:
        return pa is pb
    return abs(float(pa) - float(pb)) <= tol

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
    return hashlib.sha256(
        json.dumps(obj, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()

def merge_sources(payloads: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    seen, out = set(), []
    for p in payloads:
        for s in p.get("meta", {}).get("source", []):
            key = (s.get("url", ""), s.get("label", ""))
            if key not in seen:
                seen.add(key)
                out.append(
                    {
                        "url": s.get("url", ""),
                        "label": s.get("label", ""),
                        "date_doc": s.get("date_doc", ""),
                    }
                )
    return out

def update_database(final_core: Dict[str, Any], sources: List[Dict[str, str]]) -> None:
    # Load existing DB or init
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            db = json.load(f)
    else:
        db = {"meta": {"last_scraped": "", "hash": "", "source": [], "generator": ""}, "cotisations": []}

    # Upsert the 'assurance_chomage' cotisation in flat cotisations list
    found = False
    for item in db.get("cotisations", []):
        if item.get("id") == "assurance_chomage":
            item.update({
                "libelle": final_core["libelle"],
                "base": final_core["base"],
                "salarial": final_core["valeurs"]["salarial"],
                "patronal": final_core["valeurs"]["patronal"],
            })
            found = True
            break
    if not found:
        db["cotisations"].append({
            "id": final_core["id"],
            "libelle": final_core["libelle"],
            "base": final_core["base"],
            "salarial": final_core["valeurs"]["salarial"],
            "patronal": final_core["valeurs"]["patronal"],
        })

    # Meta
    db["meta"]["last_scraped"] = iso_now()
    db["meta"]["generator"] = "assurancechomage/orchestrator.py"
    db["meta"]["source"] = sources
    db["meta"]["hash"] = compute_hash(db.get("cotisations", []))

    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, indent=2)

def debug_dump(payloads: List[Dict[str, Any]], sigs: List[Dict[str, Any]]) -> None:
    """Print a compact side-by-side debug list of values & sources."""
    print("\n=== DEBUG valeurs par source ===")
    for p, s in zip(payloads, sigs):
        script = p.get("__script", "?")
        patro = s["valeurs"]["patronal"]
        srcs = p.get("meta", {}).get("source", [])
        src_str = ", ".join(f'{sx.get("label","?")}<{sx.get("url","")}>' for sx in srcs) or "n/a"
        print(f"- {script:<30} patronal={patro!r}    sources=[{src_str}]")
    print("=== fin DEBUG ===\n")

def main() -> None:
    # Run scrapers
    payloads: List[Dict[str, Any]] = []
    for label, path in SCRIPTS:
        payloads.append(run_script(label, path))

    # Normalize
    sigs: List[Dict[str, Any]] = [core_signature(p) for p in payloads]

    # Debug always show what each returned
    debug_dump(payloads, sigs)

    # Compare all three
    all_equal = equal_core(sigs[0], sigs[1]) and equal_core(sigs[1], sigs[2])
    if not all_equal:
        print("MISMATCH entre les sources:", file=sys.stderr)
        for p, s in zip(payloads, sigs):
            print(f"[{p.get('__script','?')}] core={json.dumps(s, ensure_ascii=False)}", file=sys.stderr)
        raise SystemExit(2)

    # Merge sources and persist
    acquire_lock()
    try:
        merged_sources = merge_sources(payloads)
        update_database(sigs[0], merged_sources)
        print("OK: base cotisations mise à jour (Assurance Chômage).")
    finally:
        release_lock()

if __name__ == "__main__":
    main()
