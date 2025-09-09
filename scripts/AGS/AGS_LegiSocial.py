# scripts/AGS/AGS_LegiSocial.py

import json
import os
import re
import sys
import requests
from bs4 import BeautifulSoup

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
FICHIER_ENTREPRISE = os.path.join(REPO_ROOT, "config", "parametres_entreprise.json")
URL_LEGISOCIAL = "https://www.legisocial.fr/reperes-sociaux/taux-cotisations-sociales-urssaf-2025.html"
USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"


def _read_est_ett(path: str) -> bool:
    """Lit le flag ETT depuis parametres_entreprise.json; False si absent."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        return bool(
            cfg.get("PARAMETRES_ENTREPRISE", {})
            .get("conditions_cotisations", {})
            .get("est_entreprise_travail_temporaire", False)
        )
    except Exception:
        return False


def _parse_percent(txt: str) -> float | None:
    """Retourne le premier pourcentage trouvé dans txt sous forme de taux (ex: '0,30 %' -> 0.003)."""
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*%", txt)
    if not m:
        return None
    val = float(m.group(1).replace(",", "."))
    return round(val / 100.0, 6)


def _extract_ags_rate_from_cell(cell_text: str, est_ett: bool) -> float | None:
    """
    Extrait le taux AGS depuis le texte de la cellule valeur.
    - Si est_ett=True, on tente d’identifier un taux mentionné près d'« travail temporaire » ou « ETT ».
    - Sinon, on prend le premier pourcentage rencontré (cas général).
    """
    txt = " ".join(cell_text.split())
    # Chercher un taux explicitement associé aux ETT
    if est_ett:
        # 1) motif « <n>% ... travail temporaire|ETT »
        m1 = re.search(r"(\d+(?:[.,]\d+)?)\s*%[^%]{0,80}\b(travail\s+temporaire|ETT)\b", txt, flags=re.I)
        if m1:
            return round(float(m1.group(1).replace(",", ".")) / 100.0, 6)
        # 2) motif « travail temporaire|ETT ... <n>% »
        m2 = re.search(r"\b(travail\s+temporaire|ETT)\b[^%]{0,80}(\d+(?:[.,]\d+)?)\s*%", txt, flags=re.I)
        if m2:
            return round(float(m2.group(2).replace(",", ".")) / 100.0, 6)
        # fallback : premier pourcentage
        return _parse_percent(txt)

    # Cas général (hors ETT) : si deux taux existent, on prend le premier non ETT si possible
    # On récupère toutes les occurrences avec leur position
    percents = [(m.start(), m.group(1)) for m in re.finditer(r"(\d+(?:[.,]\d+)?)\s*%", txt)]
    if not percents:
        return None

    # Si une mention ETT est proche d'une occurrence, on l'écarte pour choisir l'autre
    ett_spans = [m.span() for m in re.finditer(r"\b(travail\s+temporaire|ETT)\b", txt, flags=re.I)]
    def is_near_ett(pos: int, radius: int = 90) -> bool:
        return any(abs((pos - (s+e)/2)) <= radius for (s, e) in ett_spans)

    for pos, val in percents:
        if not is_near_ett(pos):
            return round(float(val.replace(",", ".")) / 100.0, 6)

    # Sinon, on prend le tout premier pourcentage
    return round(float(percents[0][1].replace(",", ".")) / 100.0, 6)


def get_ags_payload_from_legisocial(est_ett: bool) -> dict:
    """
    Scrape LegiSocial et renvoie un payload standardisé JSON (stdout) :
    {
      "id": "ags",
      "type": "cotisation",
      "libelle": "Cotisation AGS",
      "base": "brut",
      "valeurs": {"salarial": null, "patronal": <taux ou null>},
      "meta": {"source":[{"url":URL_LEGISOCIAL,"label":"LegiSocial","date_doc":""}],"generator":"AGS_LegiSocial.py"}
    }
    """
    taux = None
    try:
        resp = requests.get(URL_LEGISOCIAL, timeout=25, headers={"User-Agent": USER_AGENT})
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        # Chercher un header h3 contenant "Cotisations chômage"
        header = None
        for h in soup.find_all(["h2", "h3"]):
            if "cotisations chômage" in h.get_text(strip=True).lower():
                header = h
                break
        if not header:
            # fallback : chercher "chômage" dans des titres proches
            for h in soup.find_all(["h2", "h3"]):
                if "chômage" in h.get_text(strip=True).lower():
                    header = h
                    break

        table = header.find_next("table") if header else None
        if not table:
            # fallback : prendre la première table qui contient "AGS"
            for t in soup.find_all("table"):
                if "AGS" in t.get_text(" ", strip=True):
                    table = t
                    break

        if not table:
            raise RuntimeError("Table des cotisations chômage/AGS introuvable sur LegiSocial.")

        # Parcourir les lignes pour trouver celle de l'AGS
        for tr in table.find_all("tr"):
            tds = tr.find_all(["td", "th"])
            if not tds:
                continue
            lib = tds[0].get_text(" ", strip=True)
            if "AGS" in lib.upper():
                # La cellule de valeur est souvent la dernière colonne (employeur)
                cell_text = " ".join([td.get_text(" ", strip=True) for td in tds[1:]])
                taux = _extract_ags_rate_from_cell(cell_text, est_ett)
                break

    except Exception:
        taux = None

    payload = {
        "id": "ags",
        "type": "cotisation",
        "libelle": "Cotisation AGS",
        "base": "brut",
        "valeurs": {"salarial": None, "patronal": taux},
        "meta": {
            "source": [{"url": URL_LEGISOCIAL, "label": "LegiSocial", "date_doc": ""}],
            "generator": "AGS_LegiSocial.py",
        },
    }
    return payload


if __name__ == "__main__":
    est_ett = _read_est_ett(FICHIER_ENTREPRISE)
    payload = get_ags_payload_from_legisocial(est_ett)
    print(json.dumps(payload, ensure_ascii=False))
