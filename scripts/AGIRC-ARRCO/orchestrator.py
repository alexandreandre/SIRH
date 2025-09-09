# scripts/AGIRC-ARRCO/orchestrator.py

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
    ("AGIRC-ARRCO.py", os.path.join(os.path.dirname(__file__), "AGIRC-ARRCO.py")),
    ("AGIRC-ARRCO_LegiSocial.py", os.path.join(os.path.dirname(__file__), "AGIRC-ARRCO_LegiSocial.py")),
    ("AGIRC-ARRCO_AI.py", os.path.join(os.path.dirname(__file__), "AGIRC-ARRCO_AI.py")),
]

EXPECTED_IDS = [
    "retraite_comp_t1",
    "retraite_comp_t2",
    "ceg_t1",
    "ceg_t2",
    "cet",
    "apec",
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
        payload["__script"] = label
        return payload
    except Exception as e:
        print(
            f"[ERREUR] Sortie non-JSON depuis {label}: {e}\n---stdout---\n{out}\n-------------",
            file=sys.stderr,
        )
        raise SystemExit(2)

def core_from_bundle(payload: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """
    From a bundle payload:
    {
      id: "agirc_arrco_bundle",
      items: [ {id, base, libelle, valeurs:{salarial,patronal}}, ... ]
    }
    Return dict keyed by cotisation id with normalized values (rounded).
    """
    if payload.get("id") != "agirc_arrco_bundle" or payload.get("type") != "cotisation_bundle":
        raise SystemExit("Payload inattendu: bundle AGIRC-ARRCO requis.")
    items = payload.get("items", [])
    out: Dict[str, Dict[str, Any]] = {}
    for it in items:
        _id = it.get("id")
        if not _id:
            continue
        sal = it.get("valeurs", {}).get("salarial", None)
        pat = it.get("valeurs", {}).get("patronal", None)
        sal = None if sal is None else round(float(sal), 6)
        pat = None if pat is None else round(float(pat), 6)
        out[_id] = {
            "id": _id,
            "type": "cotisation",
            "libelle": it.get("libelle"),
            "base": it.get("base"),
            "valeurs": {"salarial": sal, "patronal": pat},
        }
    return out

def equal_item(a: Dict[str, Any], b: Dict[str, Any], tol: float = 1e-9) -> bool:
    for k in ("id", "type", "libelle", "base"):
        if a.get(k) != b.get(k):
            return False
    sa, pa = a["valeurs"]["salarial"], a["valeurs"]["patronal"]
    sb, pb = b["valeurs"]["salarial"], b["valeurs"]["patronal"]
    # Both might be None if a scraper failed a value (we disallow that below)
    if (sa is None) != (sb is None):
        return False
    if (pa is None) != (pb is None):
        return False
    if sa is not None and abs(float(sa) - float(sb)) > tol:
        return False
    if pa is not None and abs(float(pa) - float(pb)) > tol:
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
    return hashlib.sha256(
        json.dumps(obj, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()

def merge_sources(payloads: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    seen, out = set(), []
    for p in payloads:
        # sources at bundle level
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
        # sources at item level
        for it in p.get("items", []):
            for s in it.get("meta", {}).get("source", []):
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

def fmt(v):
    if v is None:
        return "None"
    try:
        return f"{float(v):.5f}"
    except Exception:
        return str(v)

def debug_compare(per_source: List[Tuple[str, Dict[str, Dict[str, Any]]]]) -> bool:
    """
    Print side-by-side values for each expected id.
    Return True if all equal & complete, else False.
    """
    all_ok = True
    print("\n=== Comparaison détaillée (AGIRC-ARRCO) ===")
    for cid in EXPECTED_IDS:
        line = [f"{cid}:"]
        # Collect values from sources
        vals = []
        metas = []
        for label, core in per_source:
            it = core.get(cid)
            if not it:
                vals.append((label, None, None))
                metas.append((label, "n/a"))
                continue
            sal = it["valeurs"]["salarial"]
            pat = it["valeurs"]["patronal"]
            vals.append((label, sal, pat))
        # Print one line
        for label, sal, pat in vals:
            line.append(f"{label}[S:{fmt(sal)}|P:{fmt(pat)}]")
        print("  " + "  |  ".join(line))
        # Equality check + completeness
        if any(sal is None or pat is None for _, sal, pat in vals):
            all_ok = False
            print(f"  -> MISSING VALUES for {cid}", file=sys.stderr)
            continue
        a = {
            "id": cid,
            "type": "cotisation",
            "libelle": per_source[0][1][cid]["libelle"],
            "base": per_source[0][1][cid]["base"],
            "valeurs": {
                "salarial": per_source[0][1][cid]["valeurs"]["salarial"],
                "patronal": per_source[0][1][cid]["valeurs"]["patronal"],
            },
        }
        for _, core in per_source[1:]:
            b = core[cid]
            if not equal_item(a, b):
                all_ok = False
                print(f"  -> MISMATCH for {cid}", file=sys.stderr)
                break
    print("=== Fin comparaison ===\n")
    return all_ok

def update_database(final_core: Dict[str, Dict[str, Any]], sources: List[Dict[str, str]]) -> None:
    # Load existing DB or init
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            db = json.load(f)
    else:
        db = {"meta": {"last_scraped": "", "hash": "", "source": [], "generator": ""}, "cotisations": []}

    # Upsert each cotisation
    for cid in EXPECTED_IDS:
        item = final_core[cid]
        found = False
        for row in db.get("cotisations", []):
            if row.get("id") == cid:
                row.update({
                    "libelle": item["libelle"],
                    "base": item["base"],
                    "salarial": item["valeurs"]["salarial"],
                    "patronal": item["valeurs"]["patronal"],
                })
                found = True
                break
        if not found:
            db["cotisations"].append({
                "id": cid,
                "libelle": item["libelle"],
                "base": item["base"],
                "salarial": item["valeurs"]["salarial"],
                "patronal": item["valeurs"]["patronal"],
            })

    # Meta
    db["meta"]["last_scraped"] = iso_now()
    db["meta"]["generator"] = "AGIRC-ARRCO/orchestrator.py"
    db["meta"]["source"] = sources
    db["meta"]["hash"] = compute_hash(db.get("cotisations", []))

    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, indent=2)

def main() -> None:
    # Run scrapers
    payloads_labeled: List[Tuple[str, Dict[str, Any]]] = []
    for label, path in SCRIPTS:
        payloads_labeled.append((label, run_script(label, path)))

    # Normalize to core per script
    cores_labeled: List[Tuple[str, Dict[str, Dict[str, Any]]]] = []
    for label, payload in payloads_labeled:
        core = core_from_bundle(payload)
        # Ensure presence of all expected ids
        missing = [cid for cid in EXPECTED_IDS if cid not in core]
        if missing:
            print(f"[ERREUR] {label}: ids manquants {missing}", file=sys.stderr)
            raise SystemExit(2)
        cores_labeled.append((label, core))

    # Debug side-by-side + equality
    if not debug_compare(cores_labeled):
        raise SystemExit(2)

    # If all good -> write DB
    acquire_lock()
    try:
        merged_sources = merge_sources([p for _, p in payloads_labeled])
        # Use the first source's core as final (since all equal)
        final_core = cores_labeled[0][1]
        update_database(final_core, merged_sources)
        print("OK: base cotisations mise à jour (AGIRC-ARRCO).")
    finally:
        release_lock()

if __name__ == "__main__":
    main()
