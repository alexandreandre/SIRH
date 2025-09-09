# scripts/fraispro/orchestrator.py

import json
import os
import sys
import hashlib
import subprocess
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DATA_FILE = os.path.join(REPO_ROOT, "data", "frais_pro.json")
LOCK_FILE = os.path.join(REPO_ROOT, "data", ".lock")

SCRIPTS = [
    os.path.join(os.path.dirname(__file__), "fraispro.py"),
    #os.path.join(os.path.dirname(__file__), "fraispro_LegiSocial.py"),
    #os.path.join(os.path.dirname(__file__), "fraispro_AI.py"),  
]


# ---------- Utils ----------
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


def _f(v: Any) -> Optional[float]:
    if v is None:
        return None
    try:
        return round(float(v), 6)
    except Exception:
        return None


def _norm_repas(d: Dict[str, Any]) -> Dict[str, Optional[float]]:
    d = d or {}
    return {
        "sur_lieu_travail": _f(d.get("sur_lieu_travail")),
        "hors_locaux_avec_restaurant": _f(d.get("hors_locaux_avec_restaurant")),
        "hors_locaux_sans_restaurant": _f(d.get("hors_locaux_sans_restaurant")),
    }


def _norm_petit_dep(lst: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out = []
    for x in lst or []:
        out.append({"km_min": int(x.get("km_min")), "km_max": int(x.get("km_max")), "montant": _f(x.get("montant"))})
    out.sort(key=lambda z: (z["km_min"], z["km_max"]))
    return out


def _norm_metropole(lst: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out = []
    for x in lst or []:
        out.append({
            "periode_sejour": str(x.get("periode_sejour", "")).strip().lower(),
            "repas": _f(x.get("repas")),
            "logement_paris_banlieue": _f(x.get("logement_paris_banlieue")),
            "logement_province": _f(x.get("logement_province")),
        })
    out.sort(key=lambda z: z["periode_sejour"])
    return out


def _norm_outre_mer(lst: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out = []
    for x in lst or []:
        out.append({
            "periode_sejour": str(x.get("periode_sejour", "")).strip().lower(),
            "hebergement": _f(x.get("hebergement")),
            "repas": _f(x.get("repas")),
        })
    out.sort(key=lambda z: z["periode_sejour"])
    return out


def _norm_mutation(d: Dict[str, Any]) -> Dict[str, Any]:
    d = d or {}
    hp = (d.get("hebergement_provisoire") or {})
    hd = (d.get("hebergement_definitif") or {})
    return {
        "hebergement_provisoire": {"montant_par_jour": _f(hp.get("montant_par_jour"))},
        "hebergement_definitif": {
            "frais_installation": _f(hd.get("frais_installation")),
            "majoration_par_enfant": _f(hd.get("majoration_par_enfant")),
            "plafond_total": _f(hd.get("plafond_total")),
        },
    }


def _norm_mobilite(d: Dict[str, Any]) -> Dict[str, Any]:
    d = d or {}
    priv = d.get("employeurs_prives") or {}
    pubs = []
    for x in d.get("employeurs_publics") or []:
        pubs.append({
            "jours_utilises": str(x.get("jours_utilises", "")).strip().lower(),
            "montant_annuel": _f(x.get("montant_annuel")),
        })
    pubs.sort(key=lambda z: z["jours_utilises"])
    return {
        "employeurs_prives": {
            "limite_base": _f(priv.get("limite_base")),
            "limite_cumul_transport_public": _f(priv.get("limite_cumul_transport_public")),
            "limite_cumul_carburant_total": _f(priv.get("limite_cumul_carburant_total")),
            "limite_cumul_carburant_part_carburant": _f(priv.get("limite_cumul_carburant_part_carburant")),
        },
        "employeurs_publics": pubs,
    }


def _norm_teletravail(d: Dict[str, Any]) -> Dict[str, Any]:
    d = d or {}
    sans = d.get("indemnite_sans_accord") or {}
    avec = d.get("indemnite_avec_accord") or {}
    mat = d.get("materiel_informatique_perso") or {}
    return {
        "indemnite_sans_accord": {
            "par_jour": _f(sans.get("par_jour")),
            "limite_mensuelle": _f(sans.get("limite_mensuelle")),
            "par_mois_pour_1_jour_semaine": _f(sans.get("par_mois_pour_1_jour_semaine")),
        },
        "indemnite_avec_accord": {k: _f(v) for k, v in avec.items()} if isinstance(avec, dict) else {},
        "materiel_informatique_perso": {"montant_mensuel": _f(mat.get("montant_mensuel"))},
    }


def core_signature(payload: Dict[str, Any]) -> Dict[str, Any]:
    if payload.get("id") != "frais_pro":
        raise SystemExit("id attendu 'frais_pro'")
    sections = payload.get("sections", {}) or {}
    return {
        "id": "frais_pro",
        "sections": {
            "repas": _norm_repas(sections.get("repas")),
            "petit_deplacement": _norm_petit_dep(sections.get("petit_deplacement")),
            "grand_deplacement": {
                "metropole": _norm_metropole((sections.get("grand_deplacement") or {}).get("metropole")),
                "outre_mer_groupe1": _norm_outre_mer((sections.get("grand_deplacement") or {}).get("outre_mer_groupe1")),
                "outre_mer_groupe2": _norm_outre_mer((sections.get("grand_deplacement") or {}).get("outre_mer_groupe2")),
            },
            "mutation_professionnelle": _norm_mutation(sections.get("mutation_professionnelle")),
            "mobilite_durable": _norm_mobilite(sections.get("mobilite_durable")),
            "teletravail": _norm_teletravail(sections.get("teletravail")),
        },
    }


def _eq_float(a: Optional[float], b: Optional[float], tol: float = 1e-6) -> bool:
    if a is None or b is None:
        return a is b
    return abs(float(a) - float(b)) <= tol


def _eq_repas(a: Dict[str, Any], b: Dict[str, Any]) -> bool:
    return all(_eq_float(a.get(k), b.get(k)) for k in ("sur_lieu_travail", "hors_locaux_avec_restaurant", "hors_locaux_sans_restaurant"))


def _eq_list_num(a: List[Dict[str, Any]], b: List[Dict[str, Any]], keys_num: Tuple[str, ...]) -> bool:
    if len(a) != len(b):
        return False
    for x, y in zip(a, b):
        for k in keys_num:
            if not _eq_float(x.get(k), y.get(k)):
                return False
    return True


def _eq_petit_dep(a: List[Dict[str, Any]], b: List[Dict[str, Any]]) -> bool:
    if len(a) != len(b):
        return False
    for x, y in zip(a, b):
        if x["km_min"] != y["km_min"] or x["km_max"] != y["km_max"]:
            return False
        if not _eq_float(x["montant"], y["montant"]):
            return False
    return True


def _eq_metropole(a: List[Dict[str, Any]], b: List[Dict[str, Any]]) -> bool:
    if len(a) != len(b):
        return False
    for x, y in zip(a, b):
        if x["periode_sejour"] != y["periode_sejour"]:
            return False
        if not (_eq_float(x["repas"], y["repas"]) and _eq_float(x["logement_paris_banlieue"], y["logement_paris_banlieue"]) and _eq_float(x["logement_province"], y["logement_province"])):
            return False
    return True


def _eq_outre_mer(a: List[Dict[str, Any]], b: List[Dict[str, Any]]) -> bool:
    if len(a) != len(b):
        return False
    for x, y in zip(a, b):
        if x["periode_sejour"] != y["periode_sejour"]:
            return False
        if not (_eq_float(x["hebergement"], y["hebergement"]) and _eq_float(x["repas"], y["repas"])):
            return False
    return True


def _eq_mutation(a: Dict[str, Any], b: Dict[str, Any]) -> bool:
    return (
        _eq_float(a["hebergement_provisoire"].get("montant_par_jour"), b["hebergement_provisoire"].get("montant_par_jour"))
        and _eq_float(a["hebergement_definitif"].get("frais_installation"), b["hebergement_definitif"].get("frais_installation"))
        and _eq_float(a["hebergement_definitif"].get("majoration_par_enfant"), b["hebergement_definitif"].get("majoration_par_enfant"))
        and _eq_float(a["hebergement_definitif"].get("plafond_total"), b["hebergement_definitif"].get("plafond_total"))
    )


def _eq_mobilite(a: Dict[str, Any], b: Dict[str, Any]) -> bool:
    pa, pb = a["employeurs_prives"], b["employeurs_prives"]
    if not all(_eq_float(pa.get(k), pb.get(k)) for k in ("limite_base", "limite_cumul_transport_public", "limite_cumul_carburant_total", "limite_cumul_carburant_part_carburant")):
        return False
    la, lb = a["employeurs_publics"], b["employeurs_publics"]
    if len(la) != len(lb):
        return False
    for x, y in zip(la, lb):
        if x["jours_utilises"] != y["jours_utilises"]:
            return False
        if not _eq_float(x["montant_annuel"], y["montant_annuel"]):
            return False
    return True


def _eq_teletravail(a: Dict[str, Any], b: Dict[str, Any]) -> bool:
    sa, sb = a["indemnite_sans_accord"], b["indemnite_sans_accord"]
    if not all(_eq_float(sa.get(k), sb.get(k)) for k in ("par_jour", "limite_mensuelle", "par_mois_pour_1_jour_semaine")):
        return False
    # Les autres blocs peuvent varier selon les pages; on tolère structure identique après normalisation
    aa, ab = a.get("indemnite_avec_accord", {}), b.get("indemnite_avec_accord", {})
    if set(aa.keys()) != set(ab.keys()):
        return False
    for k in aa.keys():
        if not _eq_float(_f(aa[k]), _f(ab[k])):
            return False
    ma, mb = a["materiel_informatique_perso"], b["materiel_informatique_perso"]
    return _eq_float(ma.get("montant_mensuel"), mb.get("montant_mensuel"))


def equal_core(a: Dict[str, Any], b: Dict[str, Any]) -> bool:
    sa, sb = a["sections"], b["sections"]
    if not _eq_repas(sa["repas"], sb["repas"]):
        return False
    if not _eq_petit_dep(sa["petit_deplacement"], sb["petit_deplacement"]):
        return False
    ga, gb = sa["grand_deplacement"], sb["grand_deplacement"]
    if not _eq_metropole(ga["metropole"], gb["metropole"]):
        return False
    if not _eq_outre_mer(ga["outre_mer_groupe1"], gb["outre_mer_groupe1"]):
        return False
    if not _eq_outre_mer(ga["outre_mer_groupe2"], gb["outre_mer_groupe2"]):
        return False
    if not _eq_mutation(sa["mutation_professionnelle"], sb["mutation_professionnelle"]):
        return False
    if not _eq_mobilite(sa["mobilite_durable"], sb["mobilite_durable"]):
        return False
    if not _eq_teletravail(sa["teletravail"], sb["teletravail"]):
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


def _ensure_db_shape(db: Any) -> Dict[str, Any]:
    if not isinstance(db, dict):
        db = {}
    if "meta" not in db or not isinstance(db["meta"], dict):
        db["meta"] = {"last_scraped": "", "hash": "", "source": [], "generator": ""}
    if "FRAIS_PRO" not in db or not isinstance(db["FRAIS_PRO"], list):
        db["FRAIS_PRO"] = []
    return db


def merge_sources(payloads: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    seen, out = set(), []
    for p in payloads:
        for s in p.get("meta", {}).get("source", []):
            key = (s.get("url", ""), s.get("label", ""))
            if key not in seen:
                seen.add(key)
                out.append({"url": s.get("url", ""), "label": s.get("label", ""), "date_doc": s.get("date_doc", "")})
    return out


def update_database(final_core: Dict[str, Any], sources: List[Dict[str, str]]) -> None:
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                db = json.load(f)
        except Exception:
            db = {}
    else:
        db = {}

    db = _ensure_db_shape(db)

    # upsert unique entrée frais_pro
    found = False
    for item in db["FRAIS_PRO"]:
        if item.get("id") == "frais_pro":
            item.update({
                "libelle": "Frais professionnels",
                "sections": final_core["sections"],
            })
            found = True
            break
    if not found:
        db["FRAIS_PRO"].append({
            "id": "frais_pro",
            "libelle": "Frais professionnels",
            "sections": final_core["sections"],
        })

    db["meta"]["last_scraped"] = iso_now()
    db["meta"]["generator"] = "fraispro/orchestrator.py"
    db["meta"]["source"] = sources
    db["meta"]["hash"] = compute_hash(db["FRAIS_PRO"])

    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, indent=2)


def _head_repas(s: Dict[str, Any]) -> str:
    r = s["sections"]["repas"]
    return f"repas[site={r.get('sur_lieu_travail')}, resto={r.get('hors_locaux_avec_restaurant')}, hors_locaux={r.get('hors_locaux_sans_restaurant')}]"


def debug_mismatch(payloads: List[Dict[str, Any]], sigs: List[Dict[str, Any]]) -> None:
    print("MISMATCH frais professionnels entre sources:", file=sys.stderr)
    for p, s in zip(payloads, sigs):
        script = p.get("__script", "?")
        print(f"- {script}: {_head_repas(s)}", file=sys.stderr)


def debug_success(sigs: List[Dict[str, Any]]) -> None:
    print(f"OK: concordance frais pro => {_head_repas(sigs[0])}")


# ---------- Main ----------
def main() -> None:
    payloads = [run_script(p) for p in SCRIPTS]
    sigs = [core_signature(p) for p in payloads]

    ok = True
    for i in range(len(sigs) - 1):
        if not equal_core(sigs[i], sigs[i + 1]):
            ok = False
            break

    if not ok:
        debug_mismatch(payloads, sigs)
        raise SystemExit(2)

    debug_success(sigs)

    acquire_lock()
    try:
        update_database(sigs[0], merge_sources(payloads))
        print("OK: base frais_pro.json mise à jour.")
    finally:
        release_lock()


if __name__ == "__main__":
    main()
