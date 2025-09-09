# scripts/CSG/orchestrator.py

import json
import os
import sys
import hashlib
import subprocess
from datetime import datetime, timezone
from typing import Any, Dict, List

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DATA_FILE = os.path.join(REPO_ROOT, "data", "cotisations.json")
LOCK_FILE = os.path.join(REPO_ROOT, "data", ".lock")

SCRIPTS = [
    os.path.join(os.path.dirname(__file__), "CSG.py"),
    os.path.join(os.path.dirname(__file__), "CSG_LegiSocial.py"),
    os.path.join(os.path.dirname(__file__), "CSG_AI.py"),  # IA optionnelle: laissez, ou commentez si besoin
]


def iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def run_script(path: str) -> Dict[str, Any]:
    """Exécute un scraper et récupère son JSON depuis stdout."""
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
    """Noyau comparable pour CSG/CRDS."""
    if payload.get("id") != "csg":
        raise SystemExit("id attendu 'csg'")
    val = payload.get("valeurs", {})
    sal = val.get("salarial")
    patro = val.get("patronal")
    # Normalisation
    sal_norm = None
    if isinstance(sal, dict):
        sal_norm = {
            "deductible": None if sal.get("deductible") is None else round(float(sal.get("deductible")), 6),
            "non_deductible": None if sal.get("non_deductible") is None else round(float(sal.get("non_deductible")), 6),
        }
    return {
        "id": "csg",
        "type": payload.get("type"),
        "libelle": payload.get("libelle"),
        "base": payload.get("base"),
        "valeurs": {
            "salarial": sal_norm,
            "patronal": None if patro is None else round(float(patro), 6),  # attendu None
        },
    }


def equal_core(a: Dict[str, Any], b: Dict[str, Any], tol: float = 1e-9) -> bool:
    for k in ("id", "type", "libelle", "base"):
        if a.get(k) != b.get(k):
            return False
    sa, sb = a["valeurs"]["salarial"], b["valeurs"]["salarial"]
    # Les deux doivent être des dicts avec deux clés, ou None simultanément
    if (sa is None) or (sb is None):
        return sa is sb
    for k in ("deductible", "non_deductible"):
        va, vb = sa.get(k), sb.get(k)
        if (va is None) or (vb is None):
            if va is not vb:
                return False
        else:
            if abs(float(va) - float(vb)) > tol:
                return False
    # patronal est attendu None
    return a["valeurs"]["patronal"] is b["valeurs"]["patronal"]


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
                out.append(
                    {"url": s.get("url", ""), "label": s.get("label", ""), "date_doc": s.get("date_doc", "")}
                )
    return out


def update_database(final_core: Dict[str, Any], sources: List[Dict[str, str]]) -> None:
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            db = json.load(f)
    else:
        db = {"meta": {"last_scraped": "", "hash": "", "source": [], "generator": ""}, "cotisations": []}

    # upsert CSG dans la liste "cotisations"
    found = False
    for item in db.get("cotisations", []):
        if item.get("id") == "csg":
            item.update({
                "libelle": final_core["libelle"],
                "base": final_core["base"],
                "salarial": final_core["valeurs"]["salarial"],   # dict {"deductible": x, "non_deductible": y}
                "patronal": final_core["valeurs"]["patronal"],   # None attendu
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

    db["meta"]["last_scraped"] = iso_now()
    db["meta"]["generator"] = "CSG/orchestrator.py"
    db["meta"]["source"] = sources
    db["meta"]["hash"] = compute_hash(db.get("cotisations", []))

    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, indent=2)


def debug_mismatch(payloads: List[Dict[str, Any]], sigs: List[Dict[str, Any]]) -> None:
    print("MISMATCH entre les sources:", file=sys.stderr)
    # Vue rapide
    def short(s: Dict[str, Any]) -> str:
        sal = s["valeurs"]["salarial"]
        if sal is None:
            return "salarial=None"
        return f"ded={sal.get('deductible')} | non_ded={sal.get('non_deductible')}"
    line = " | ".join(f"{p.get('__script','?')}=[{short(s)}]" for p, s in zip(payloads, sigs))
    print(f"  ► Comparatif: {line}", file=sys.stderr)
    # Détails
    for p, s in zip(payloads, sigs):
        script = p.get("__script", "?")
        srcs = p.get("meta", {}).get("source", [])
        src = srcs[0]["url"] if srcs else ""
        print(f"- {script} -> {json.dumps(s['valeurs'], ensure_ascii=False)} | source={src}", file=sys.stderr)


def debug_success(payloads: List[Dict[str, Any]], sigs: List[Dict[str, Any]]) -> None:
    def short(s: Dict[str, Any]) -> str:
        sal = s["valeurs"]["salarial"]
        return f"ded={sal.get('deductible')} | non_ded={sal.get('non_deductible')}"
    line = " | ".join(f"{p.get('__script','?')}=[{short(s)}]" for p, s in zip(payloads, sigs))
    print(f"OK: concordance CSG/CRDS => {line}")


def main() -> None:
    payloads = [run_script(p) for p in SCRIPTS]
    sigs = [core_signature(p) for p in payloads]

    # Exiger concordance pairwise
    ok = True
    for i in range(len(sigs) - 1):
        if not equal_core(sigs[i], sigs[i + 1]):
            ok = False
            break

    if not ok:
        debug_mismatch(payloads, sigs)
        raise SystemExit(2)

    debug_success(payloads, sigs)

    acquire_lock()
    try:
        update_database(sigs[0], merge_sources(payloads))
        print("OK: base cotisations mise à jour (CSG/CRDS).")
    finally:
        release_lock()


if __name__ == "__main__":
    main()
