# scripts/MMIDpatronal/MMIDpatronal.py
import json
import re
from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup

URL_URSSAF = "https://www.urssaf.fr/accueil/outils-documentation/taux-baremes/taux-cotisations-secteur-prive.html"

def iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def _fetch_page(url: str) -> BeautifulSoup:
    r = requests.get(
        url,
        timeout=20,
        headers={
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "fr-FR,fr;q=0.9",
        },
    )
    r.raise_for_status()
    return BeautifulSoup(r.text, "html.parser")

def _find_employeur_section(soup: BeautifulSoup):
    for article in soup.find_all("article"):
        h2 = article.find("h2", class_="h4-like")
        if h2 and "taux de cotisations employeur" in h2.get_text(strip=True).lower():
            return article
    return None

def _to_rate_percent_str(s: str) -> float | None:
    if not s:
        return None
    try:
        return round(float(s.replace(",", ".")) / 100.0, 6)
    except Exception:
        return None

def scrape_maladie_rates() -> dict[str, float | None]:
    """
    Extrait les deux taux patronaux Assurance maladie:
      - patronal_plein
      - patronal_reduit
    """
    try:
        soup = _fetch_page(URL_URSSAF)
        section = _find_employeur_section(soup)
        if not section:
            raise ValueError("Section employeur introuvable.")
        rate_plein, rate_reduit = None, None

        for row in section.find_all("tr", class_="table_custom__tbody"):
            th = row.find("th")
            if th and "Assurance maladie" in th.get_text(strip=True):
                td = row.find("td")
                if not td:
                    break
                txt = td.get_text(" ", strip=True)
                m_plein = re.search(r"taux\s*plein\s*à\s*([\d.,]+)\s*%", txt, flags=re.IGNORECASE)
                m_reduit = re.search(r"taux\s*r[ée]duit\s*à\s*([\d.,]+)\s*%", txt, flags=re.IGNORECASE)
                if m_plein:
                    rate_plein = _to_rate_percent_str(m_plein.group(1))
                if m_reduit:
                    rate_reduit = _to_rate_percent_str(m_reduit.group(1))
                break

        return {"patronal_plein": rate_plein, "patronal_reduit": rate_reduit}
    except Exception:
        return {"patronal_plein": None, "patronal_reduit": None}

def build_payload(rates: dict[str, float | None]) -> dict:
    return {
        "id": "securite_sociale_maladie",
        "type": "cotisation",
        "libelle": "Sécurité sociale - Maladie, Maternité, Invalidité, Décès",
        "base": "brut",
        "valeurs": {
            "salarial": None,
            "patronal_plein": rates.get("patronal_plein"),
            "patronal_reduit": rates.get("patronal_reduit"),
        },
        "meta": {
            "source": [{"url": URL_URSSAF, "label": "URSSAF — Taux secteur privé", "date_doc": ""}],
            "scraped_at": iso_now(),
            "generator": "scripts/MMIDpatronal/MMIDpatronal.py",
            "method": "primary",
        },
    }

def main() -> None:
    rates = scrape_maladie_rates()
    payload = build_payload(rates)
    print(json.dumps(payload, ensure_ascii=False))

if __name__ == "__main__":
    main()
