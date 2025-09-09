# scripts/CSG/CSG.py

import json
import re
from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup

URL_URSSAF = "https://www.urssaf.fr/accueil/outils-documentation/taux-baremes/taux-cotisations-secteur-prive.html"


def iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_percent_to_rate(text: str):
    if not text:
        return None
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*%", text)
    if not m:
        return None
    try:
        return round(float(m.group(1).replace(",", ".")) / 100.0, 6)
    except Exception:
        return None


def get_taux_csg() -> dict | None:
    """
    Scrape URSSAF: retourne {
        "deductible": float | None,
        "non_deductible": float | None
    }
    où:
      - deductible = CSG non imposable
      - non_deductible = CSG imposable + CRDS
    """
    try:
        r = requests.get(
            URL_URSSAF,
            timeout=25,
            headers={
                "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "fr-FR,fr;q=0.9",
            },
        )
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")

        # Section "Taux de cotisations salarié"
        salarie_section = None
        for article in soup.find_all("article"):
            h2 = article.find("h2", class_="h4-like")
            if h2 and "taux de cotisations salarié" in h2.get_text(strip=True).lower():
                salarie_section = article
                break
        if not salarie_section:
            return None

        rows = salarie_section.find_all("tr", class_="table_custom__tbody")

        targets = {
            "csg_imposable": "CSG imposable",
            "csg_non_imposable": "CSG non imposable",
            "crds": "CRDS",
        }
        found = {"csg_imposable": None, "csg_non_imposable": None, "crds": None}

        for row in rows:
            th = row.find("th")
            td = row.find("td")
            if not th or not td:
                continue
            label = th.get_text(strip=True)
            val = parse_percent_to_rate(td.get_text(strip=True))
            if val is None:
                continue
            for key, needle in targets.items():
                if needle in label:
                    found[key] = val

        if any(found[k] is None for k in found):
            return None

        taux_deductible = found["csg_non_imposable"]
        taux_non_deductible = round((found["csg_imposable"] or 0) + (found["crds"] or 0), 6)

        return {"deductible": taux_deductible, "non_deductible": taux_non_deductible}
    except Exception:
        return None


def build_payload(taux: dict | None) -> dict:
    # Structure unifiée pour l’orchestrateur
    # valeurs.salarial contient un objet {deductible, non_deductible}
    vals = {"salarial": None, "patronal": None}
    if taux is not None:
        vals["salarial"] = {"deductible": taux.get("deductible"), "non_deductible": taux.get("non_deductible")}
    return {
        "id": "csg",
        "type": "cotisation",
        "libelle": "CSG/CRDS",
        "base": "brut",
        "valeurs": vals,
        "meta": {
            "source": [{"url": URL_URSSAF, "label": "URSSAF — Taux secteur privé", "date_doc": ""}],
            "scraped_at": iso_now(),
            "generator": "scripts/CSG/CSG.py",
            "method": "primary",
        },
    }


if __name__ == "__main__":
    taux = get_taux_csg()
    payload = build_payload(taux)
    print(json.dumps(payload, ensure_ascii=False))
