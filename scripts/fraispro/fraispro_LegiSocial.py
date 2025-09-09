# scripts/fraispro/fraispro_LegiSocial.py

import json
import re
import sys
import unicodedata
from datetime import datetime, timezone
from typing import Any, Dict, List

import requests
from bs4 import BeautifulSoup

URL_LEGISOCIAL = "https://www.legisocial.fr/reperes-sociaux/allocations-forfaitaires-frais-professionnels-2025.html"


# ---------- Utils ----------
def iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def norm(txt: str) -> str:
    if not txt:
        return ""
    txt = unicodedata.normalize("NFD", txt)
    txt = "".join(c for c in txt if unicodedata.category(c) != "Mn")
    return txt.lower().replace("\xa0", " ").replace("\u202f", " ").strip()


def parse_valeur_numerique(text: str) -> float:
    if not text:
        return 0.0
    cleaned = (
        text.replace("€", "")
        .replace("\xa0", "")
        .replace("\u202f", "")
        .replace(" ", "")
        .replace(",", ".")
    )
    m = re.search(r"([0-9]+\.?[0-9]*)", cleaned)
    return float(m.group(1)) if m else 0.0


# ---------- Scrapers robustes, mais en conservant la logique d'origine ----------
def scrape_repas_legisocial(soup: BeautifulSoup) -> Dict[str, float]:
    """
    Même logique fonctionnelle que le script de base, mais on ne dépend plus d'un H2 précis.
    On parcourt tous les tableaux et on capte les 3 libellés repas.
    """
    data: Dict[str, float] = {}
    wanted = {
        "sur_lieu_travail": (
            "sur son lieu de travail",
            "sur le lieu de travail",
        ),
        "hors_locaux_sans_restaurant": (
            "non contraint de prendre son repas au restaurant",
            "non contraint",
            "hors des locaux sans possibilite",
            "hors locaux sans restaurant",
        ),
        "hors_locaux_avec_restaurant": (
            "repas au restaurant",
            "au restaurant",
            "contraint de prendre son repas au restaurant",
        ),
    }

    for table in soup.find_all("table"):
        for tr in table.find_all("tr"):
            tds = tr.find_all("td")
            if len(tds) != 2:
                continue
            lib = norm(tds[0].get_text(" ", strip=True))
            val = parse_valeur_numerique(tds[1].get_text(" ", strip=True))

            if not val:
                continue

            for key, variants in wanted.items():
                if any(v in lib for v in map(norm, variants)):
                    data[key] = val
        if len(data) == 3:
            break

    return data


def _collect_amounts_by_marker(soup: BeautifulSoup, marker: str, limit: int) -> List[float]:
    """
    Trouve 'limit' montants en balayant toutes les tables et lignes contenant le marqueur.
    Renvoie les montants dans l'ordre d'apparition.
    """
    mk = norm(marker)
    vals: List[float] = []
    for table in soup.find_all("table"):
        for tr in table.find_all("tr"):
            rowtxt = norm(tr.get_text(" ", strip=True))
            if mk in rowtxt:
                # récupère la dernière cellule chiffrée de la ligne
                tds = tr.find_all("td")
                if not tds:
                    continue
                nums = [parse_valeur_numerique(td.get_text(" ", strip=True)) for td in tds]
                nums = [x for x in nums if x > 0]
                if nums:
                    vals.append(nums[-1])
                    if len(vals) >= limit:
                        return vals
    return vals


def scrape_grand_deplacement_legisocial(soup: BeautifulSoup) -> Dict[str, Any]:
    """
    Reprend la logique du script de base: 3 périodes métropole,
    et pour chacune: par repas, Paris+banlieue, autres départements.
    On ne dépend pas d'un H2/Tableau unique.
    """
    data: Dict[str, Any] = {"metropole": []}
    periods = ["Pour les 3 premiers mois", "Au-delà du 3 ème mois", "Au-delà du 24 ème mois"]

    repas_vals = _collect_amounts_by_marker(soup, "par repas", 3)
    paris_vals = _collect_amounts_by_marker(
        soup, "paris et les departements des haut-de-seine, seine-saint-denis et val-de-marne", 3
    )
    province_vals = _collect_amounts_by_marker(soup, "autres departements", 3)

    n = min(len(repas_vals), len(paris_vals), len(province_vals), 3)
    for i in range(n):
        data["metropole"].append(
            {
                "periode_sejour": periods[i],
                "repas": repas_vals[i],
                "logement_paris_banlieue": paris_vals[i],
                "logement_province": province_vals[i],
            }
        )
    return data


def scrape_mutation_legisocial(soup: BeautifulSoup) -> Dict[str, Any]:
    """
    Même logique que le script de base. On balaie tous les tableaux et on capture les lignes utiles.
    """
    out: Dict[str, Any] = {"hebergement_provisoire": {}, "hebergement_definitif": {}}

    for table in soup.find_all("table"):
        for tr in table.find_all("tr"):
            tds = tr.find_all("td")
            if len(tds) != 2:
                continue
            lib = norm(tds[0].get_text(" ", strip=True))
            val_cell = tds[1]
            valtxt = val_cell.get_text(" ", strip=True)

            if "hebergement provisoire" in lib and "montant_par_jour" not in out["hebergement_provisoire"]:
                out["hebergement_provisoire"]["montant_par_jour"] = parse_valeur_numerique(valtxt)

            elif "installation dans le nouveau logement" in lib and "frais_installation" not in out["hebergement_definitif"]:
                out["hebergement_definitif"]["frais_installation"] = parse_valeur_numerique(valtxt)

            elif "majore de par enfant" in lib:
                vals = [parse_valeur_numerique(p.get_text(" ", strip=True)) for p in val_cell.find_all(["p", "span"])]
                vals = [v for v in vals if v > 0]
                if len(vals) >= 2:
                    out["hebergement_definitif"]["majoration_par_enfant"] = vals[0]
                    out["hebergement_definitif"]["plafond_total"] = vals[1]
                else:
                    # fallback si un seul nombre visible
                    v = parse_valeur_numerique(valtxt)
                    if v and "majoration_par_enfant" not in out["hebergement_definitif"]:
                        out["hebergement_definitif"]["majoration_par_enfant"] = v

    return out


# ---------- Payload ----------
def build_payload(sections: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": "frais_pro",
        "type": "frais_professionnels",
        "libelle": "Frais professionnels (LégiSocial)",
        "sections": sections,
        "meta": {
            "source": [
                {
                    "url": URL_LEGISOCIAL,
                    "label": "LégiSocial — Allocations forfaitaires frais professionnels 2025",
                    "date_doc": "",
                }
            ],
            "scraped_at": iso_now(),
            "generator": "scripts/fraispro/fraispro_LegiSocial.py",
            "method": "secondary",
        },
    }


# ---------- Main ----------
if __name__ == "__main__":
    try:
        r = requests.get(
            URL_LEGISOCIAL,
            timeout=25,
            headers={
                "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
            },
        )
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")

        # Conserver l’esprit du script de base, mais rendre la détection robuste
        repas_data = scrape_repas_legisocial(soup)
        grand_deplacement_data = scrape_grand_deplacement_legisocial(soup)
        mutation_data = scrape_mutation_legisocial(soup)

        sections = {
            "repas": repas_data,
            "petit_deplacement": [],  # non présent sur cette page
            "grand_deplacement": grand_deplacement_data,
            "mutation_professionnelle": mutation_data,
            "mobilite_durable": {"employeurs_prives": {}, "employeurs_publics": []},  # non présent
            "teletravail": {
                "indemnite_sans_accord": {},
                "indemnite_avec_accord": {},
                "materiel_informatique_perso": {},
            },  # non présent
        }

        print(json.dumps(build_payload(sections), ensure_ascii=False))
    except Exception as e:
        print(f"ERREUR: {e}", file=sys.stderr)
        # Sortie structurée pour ne pas casser l’orchestrateur
        empty_sections = {
            "repas": {},
            "petit_deplacement": [],
            "grand_deplacement": {"metropole": []},
            "mutation_professionnelle": {"hebergement_provisoire": {}, "hebergement_definitif": {}},
            "mobilite_durable": {"employeurs_prives": {}, "employeurs_publics": []},
            "teletravail": {"indemnite_sans_accord": {}, "indemnite_avec_accord": {}, "materiel_informatique_perso": {}},
        }
        print(json.dumps(build_payload(empty_sections), ensure_ascii=False))
