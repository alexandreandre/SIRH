# scripts/alloc/orchestrator.py

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
    ("alloc.py", os.path.join(os.path.dirname(__file__), "alloc.py")),
    ("alloc_AI.py", os.path.join(os.path.dirname(__file__), "alloc_AI.py")),
    ("alloc_LegiSocial.py", os.path.join(os.path.dirname(__file__), "alloc_LegiSocial.py")),
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
        payload["__script"] = label  # tag pour debug
        return payload
    except Exception as e:
        print(
            f"[ERREUR] Sortie non-JSON depuis {label}: {e}\n---stdout---\n{out}\n-------------",
            file=sys.stderr,
        )
        raise SystemExit(2)

def core_signature(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize payload to the comparable core for allocations familiales (plein+réduit)."""
    if payload.get("id") != "allocations_familiales":
        raise SystemExit("id attendu 'allocations_familiales'")
    vals = payload.get("valeurs", {}) or {}
    plein = vals.get("patronal_plein", None)
    reduit = vals.get("patronal_reduit", None)
    plein = None if plein is None else round(float(plein), 6)
    reduit = None if reduit is None else round(float(reduit), 6)
    return {
        "id": payload.get("id"),
        "type": payload.get("type"),
        "libelle": payload.get("libelle"),
        "base": payload.get("base"),
        "valeurs": {
            "salarial": None,
            "patronal_plein": plein,
            "patronal_reduit": reduit,
        },
    }

def validate_sig(sig: Dict[str, Any]) -> bool:
    """Exige que plein et réduit soient non-nuls."""
    v = sig.get("valeurs", {})
    return v.get("patronal_plein") is not None and v.get("patronal_reduit") is not None

def equal_core(a: Dict[str, Any], b: Dict[str, Any], tol: float = 1e-9) -> bool:
    for k in ("id", "type", "libelle", "base"):
        if a.get(k) != b.get(k):
            return False
    ap, ar = a["valeurs"]["patronal_plein"], a["valeurs"]["patronal_reduit"]
    bp, br = b["valeurs"]["patronal_plein"], b["valeurs"]["patronal_reduit"]
    if ap is None or bp is None or ar is None or br is None:
        return False
    return abs(float(ap) - float(bp)) <= tol and abs(float(ar) - float(br)) <= tol

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

    # Upsert the 'allocations_familiales' cotisation in flat cotisations list
    found = False
    for item in db.get("cotisations", []):
        if item.get("id") == "allocations_familiales":
            # conserve les autres champs éventuels, mais impose nos 2 taux
            item.update({
                "libelle": final_core["libelle"],
                "base": final_core["base"],
                "salarial": final_core["valeurs"]["salarial"],
                "patronal_plein": final_core["valeurs"]["patronal_plein"],
                "patronal_reduit": final_core["valeurs"]["patronal_reduit"],
            })
            found = True
            break
    if not found:
        db["cotisations"].append({
            "id": final_core["id"],
            "libelle": final_core["libelle"],
            "base": final_core["base"],
            "salarial": final_core["valeurs"]["salarial"],
            "patronal_plein": final_core["valeurs"]["patronal_plein"],
            "patronal_reduit": final_core["valeurs"]["patronal_reduit"],
        })

    # Meta
    db["meta"]["last_scraped"] = iso_now()
    db["meta"]["generator"] = "alloc/orchestrator.py"
    db["meta"]["source"] = sources
    db["meta"]["hash"] = compute_hash(db.get("cotisations", []))

    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, indent=2)

def debug_dump(payloads_labeled: List[Tuple[str, Dict[str, Any]]], sigs_labeled: List[Tuple[str, Dict[str, Any]]]) -> None:
    print("Comparaison des résultats (plein / réduit):", file=sys.stderr)
    for (label, raw), (lbl, sig) in zip(payloads_labeled, sigs_labeled):
        v = sig["valeurs"]
        plein = v["patronal_plein"]
        reduit = v["patronal_reduit"]
        srcs = raw.get("meta", {}).get("source", [])
        src_str = ", ".join(f'{s.get("label","?")}<{s.get("url","")}>' for s in srcs) or "n/a"
        print(f"- {label:>18} -> plein={plein}  réduit={reduit} | sources=[{src_str}]", file=sys.stderr)

def main() -> None:
    # Run scrapers
    payloads_labeled: List[Tuple[str, Dict[str, Any]]] = []
    for label, path in SCRIPTS:
        payloads_labeled.append((label, run_script(label, path)))

    # Normalize
    sigs_labeled: List[Tuple[str, Dict[str, Any]]] = [(lbl, core_signature(p)) for lbl, p in payloads_labeled]

    # Debug dump of values and sources
    debug_dump(payloads_labeled, sigs_labeled)

    # Validate presence (non-null) of both rates in each
    for lbl, sig in sigs_labeled:
        if not validate_sig(sig):
            print(f"[ERREUR] Valeurs manquantes dans {lbl}: {json.dumps(sig, ensure_ascii=False)}", file=sys.stderr)
            raise SystemExit(2)

    # Compare all three
    sigs = [s for _, s in sigs_labeled]
    all_equal = equal_core(sigs[0], sigs[1]) and equal_core(sigs[1], sigs[2])

    if not all_equal:
        print("MISMATCH entre les sources (plein/réduit) — arrêt sans écriture.", file=sys.stderr)
        raise SystemExit(2)

    # Merge sources and persist
    acquire_lock()
    try:
        merged_sources = merge_sources([p for _, p in payloads_labeled])
        update_database(sigs[0], merged_sources)
        v = sigs[0]["valeurs"]
        print(f"OK: base cotisations mise à jour (allocations familiales) "
              f"— confirmées par 3 sources | plein={v['patronal_plein']} réduit={v['patronal_reduit']}.")
    finally:
        release_lock()

if __name__ == "__main__":
    main()
