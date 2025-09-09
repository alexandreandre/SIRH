# scripts/Avantages/orchestrator.py

import json
import os
import sys
import math
import hashlib
import subprocess
from typing import Any, Dict, List, Tuple

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
PARAM_FILE = os.path.join(REPO_ROOT, "data", "entreprise.json")
LOCK_FILE = os.path.join(REPO_ROOT, "data", ".lock")

SCRIPTS: List[Tuple[str, str]] = [
    ("URSSAF", os.path.join(os.path.dirname(__file__), "Avantages.py")),
    ("LegiSocial", os.path.join(os.path.dirname(__file__), "Avantages_LegiSocial.py")),
    # Pour inclure l'IA, décommentez la ligne suivante :
    # ("AI", os.path.join(os.path.dirname(__file__), "Avantages_AI.py")),
]

# ------------------------------- utils -------------------------------

def run_script(label: str, path: str) -> Dict[str, Any]:
    """Run a script; return its stdout parsed as JSON if possible."""
    proc = subprocess.run(
        [sys.executable, path],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        env=os.environ.copy(),
    )
    out = (proc.stdout or "").strip()
    if proc.returncode != 0:
        # Even on non-0, try to parse stdout JSON (some scripts print payload then exit 2)
        try:
            return json.loads(out) if out else {}
        except Exception:
            print(f"\n[ERREUR] {label} a échoué (code {proc.returncode})", file=sys.stderr)
            if proc.stdout.strip():
                print("[stdout]", proc.stdout, file=sys.stderr)
            if proc.stderr.strip():
                print("[stderr]", proc.stderr, file=sys.stderr)
            raise SystemExit(2)
    try:
        return json.loads(out) if out else {}
    except Exception:
        return {}

def read_config_snapshot() -> Dict[str, Any]:
    try:
        with open(PARAM_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def to_float(x) -> float | None:
    if x is None:
        return None
    try:
        if isinstance(x, str):
            x = x.replace("\u202f","").replace("\xa0","").replace("€","").replace(" ", "").replace(",", ".")
        return float(x)
    except Exception:
        return None

def normalize_bareme(lst: Any) -> List[Dict[str, float]]:
    out: List[Dict[str, float]] = []
    if not isinstance(lst, list):
        return out
    for row in lst:
        if not isinstance(row, dict):
            continue
        rmax = to_float(row.get("remuneration_max") if "remuneration_max" in row else row.get("remuneration_max_eur"))
        v1 = to_float(row.get("valeur_1_piece") if "valeur_1_piece" in row else row.get("valeur_1_piece_eur"))
        vpp = to_float(row.get("valeur_par_piece") if "valeur_par_piece" in row else row.get("valeur_par_piece_suppl_eur"))
        if v1 is None or vpp is None:
            continue
        out.append({
            "remuneration_max_eur": rmax if rmax is not None else 9_999_999.99,
            "valeur_1_piece_eur": v1,
            "valeur_par_piece_suppl_eur": vpp,
        })
    return out

def payload_to_core(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Extract comparable core from various payload shapes or config snapshot."""
    # 1) AI payload style: {id, type:param_bundle, items:[...]}
    if isinstance(payload, dict) and payload.get("type") == "param_bundle":
        items = payload.get("items", [])
        mp = {it.get("key"): it.get("value") for it in items if isinstance(it, dict)}
        repas = to_float(mp.get("repas_valeur_forfaitaire_eur") or mp.get("repas"))
        titre = to_float(mp.get("titre_restaurant_exoneration_max_eur") or mp.get("titre_restaurant"))
        logement = normalize_bareme(mp.get("logement_bareme_forfaitaire") or mp.get("logement"))
        return {"repas": repas, "titre": titre, "logement": logement, "__src": payload.get("meta", {}).get("source", [])}

    # 2) Direct dict with keys
    if isinstance(payload, dict) and {"repas","titre_restaurant","logement"} <= set(payload.keys()):
        repas = to_float(payload.get("repas"))
        titre = to_float(payload.get("titre_restaurant"))
        logement = normalize_bareme(payload.get("logement"))
        return {"repas": repas, "titre": titre, "logement": logement, "__src": payload.get("meta", {}).get("source", [])}

    # 3) Fallback: read config snapshot style
    cfg = payload if payload else read_config_snapshot()
    try:
        av = cfg["PARAMETRES_ENTREPRISE"]["avantages_en_nature"]
        repas = to_float(av.get("repas_valeur_forfaitaire"))
        titre = to_float(av.get("titre_restaurant_exoneration_max_patronale"))
        logement = normalize_bareme(av.get("logement_bareme_forfaitaire"))
        return {"repas": repas, "titre": titre, "logement": logement, "__src": []}
    except Exception:
        return {"repas": None, "titre": None, "logement": [], "__src": []}

def cores_equal(a: Dict[str, Any], b: Dict[str, Any], tol: float = 1e-6) -> bool:
    def feq(x, y):
        if x is None or y is None:
            return x is None and y is None
        return math.isclose(float(x), float(y), rel_tol=0, abs_tol=tol)

    if not (feq(a["repas"], b["repas"]) and feq(a["titre"], b["titre"])):
        return False
    la, lb = a["logement"], b["logement"]
    if len(la) != len(lb):
        return False
    for r1, r2 in zip(la, lb):
        if not (feq(r1["remuneration_max_eur"], r2["remuneration_max_eur"]) and
                feq(r1["valeur_1_piece_eur"], r2["valeur_1_piece_eur"]) and
                feq(r1["valeur_par_piece_suppl_eur"], r2["valeur_par_piece_suppl_eur"])):
            return False
    return True

def acquire_lock():
    os.makedirs(os.path.dirname(PARAM_FILE), exist_ok=True)
    try:
        fd = os.open(LOCK_FILE, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.write(fd, b"lock")
        os.close(fd)
    except FileExistsError:
        raise SystemExit("Lock présent: écriture en cours.")

def release_lock():
    try:
        os.remove(LOCK_FILE)
    except FileNotFoundError:
        pass

def debug_mismatch(labels: List[str], cores: List[Dict[str, Any]], payloads: List[Dict[str, Any]]):
    print("MISMATCH entre les sources:", file=sys.stderr)
    for lbl, core, raw in zip(labels, cores, payloads):
        srcs = raw.get("meta", {}).get("source", []) if isinstance(raw, dict) else []
        src = ", ".join(f'{s.get("label","?")}<{s.get("url","")}>' for s in srcs) or "n/a"
        print(f"- {lbl}: repas={core['repas']} | titre={core['titre']} | logement_n={len(core['logement'])} | source=[{src}]", file=sys.stderr)
        if core["logement"]:
            first = core["logement"][0]
            print(f"    logement[0]={first}", file=sys.stderr)

def write_config_from_core(core: Dict[str, Any]):
    cfg = read_config_snapshot()
    if "PARAMETRES_ENTREPRISE" not in cfg:
        cfg["PARAMETRES_ENTREPRISE"] = {}
    av = cfg["PARAMETRES_ENTREPRISE"].setdefault("avantages_en_nature", {})

    av["repas_valeur_forfaitaire"] = core["repas"]
    av["titre_restaurant_exoneration_max_patronale"] = core["titre"]
    av["logement_bareme_forfaitaire"] = [
        {
            "remuneration_max": row["remuneration_max_eur"],
            "valeur_1_piece": row["valeur_1_piece_eur"],
            "valeur_par_piece": row["valeur_par_piece_suppl_eur"],
        } for row in core["logement"]
    ]

    with open(PARAM_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)

# ------------------------------- main -------------------------------

def main():
    labels = [lbl for lbl, _ in SCRIPTS]
    raw_payloads: List[Dict[str, Any]] = []
    for lbl, path in SCRIPTS:
        raw = run_script(lbl, path)
        if not raw:
            raw = read_config_snapshot()
        raw_payloads.append(raw)

    cores = [payload_to_core(p) for p in raw_payloads]

    # Debug side-by-side values
    print("== DEBUG comparatif ==")
    for lbl, core in zip(labels, cores):
        print(f"[{lbl}] repas={core['repas']} | titre={core['titre']} | logement_n={len(core['logement'])}")

    # Vérifie que toutes les sources actives sont égales entre elles
    all_equal = all(cores_equal(cores[0], c) for c in cores[1:])
    if not all_equal:
        debug_mismatch(labels, cores, raw_payloads)
        raise SystemExit(2)

    acquire_lock()
    try:
        write_config_from_core(cores[0])
        print("OK: paramètres 'avantages_en_nature' mis à jour (repas / titre-restaurant / logement).")
    finally:
        release_lock()

if __name__ == "__main__":
    main()
