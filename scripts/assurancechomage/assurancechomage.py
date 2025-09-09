# scripts/assurancechomage/assurancechomage.py

import json
import re
import requests
from datetime import datetime
from bs4 import BeautifulSoup

URL_URSSAF = "https://www.urssaf.fr/accueil/outils-documentation/taux-baremes/taux-cotisations-secteur-prive.html"
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

def _txt(el) -> str:
    return el.get_text(" ", strip=True) if el else ""

def _to_rate(num_str: str) -> float:
    return round(float(num_str.replace(",", ".").replace(" ", "")) / 100.0, 6)

def scrape_assurance_chomage() -> float | None:
    try:
        r = requests.get(URL_URSSAF, timeout=25, headers={"User-Agent": UA})
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "lxml")

        # Section "taux de cotisations employeur"
        target_article = None
        for art in soup.find_all("article"):
            h2 = art.find("h2", class_="h4-like")
            if h2 and "taux de cotisations employeur" in _txt(h2).lower():
                target_article = art
                break
        if not target_article:
            return None

        # Ligne "Contribution assurance chômage"
        tr_rows = target_article.find_all("tr", class_="table_custom__tbody")
        row_txt = ""
        for tr in tr_rows:
            th = tr.find("th")
            if th and "contribution assurance chômage" in _txt(th).lower():
                td = tr.find("td")
                row_txt = _txt(td)
                break
        if not row_txt:
            return None

        # Normaliser quelques caractères
        txt = row_txt.replace("\u00a0", " ").replace("\u202f", " ")

        # Deux cas datés : "Jusqu’au dd/mm/yyyy : X %" et "À partir du dd/mm/yyyy : Y %"
        re_avant = re.compile(r"jusqu[’']?au\s*(\d{1,2}\s*/\s*\d{1,2}\s*/\s*\d{4}).*?(\d+(?:,\d+)?)\s*%",
                              flags=re.IGNORECASE | re.DOTALL)
        re_apres = re.compile(r"(?:à|a)\s*partir\s*du\s*(\d{1,2}\s*/\s*\d{1,2}\s*/\s*\d{4}).*?(\d+(?:,\d+)?)\s*%",
                              flags=re.IGNORECASE | re.DOTALL)

        m1 = re_avant.search(txt)
        m2 = re_apres.search(txt)

        if m1 and m2:
            date_avant = datetime.strptime(m1.group(1).replace(" ", ""), "%d/%m/%Y").date()
            taux_avant = _to_rate(m1.group(2))
            date_apres = datetime.strptime(m2.group(1).replace(" ", ""), "%d/%m/%Y").date()
            taux_apres = _to_rate(m2.group(2))

            today = datetime.now().date()
            # si today < date_apres -> taux_avant, sinon taux_apres
            return taux_avant if today < date_apres else taux_apres

        # Fallback : prendre le premier pourcentage trouvé
        m_any = re.search(r"(\d+(?:,\d+)?)\s*%", txt)
        if m_any:
            return _to_rate(m_any.group(1))

        return None
    except Exception:
        return None

def make_payload(rate: float | None) -> dict:
    return {
        "id": "assurance_chomage",
        "type": "cotisation",
        "libelle": "Assurance Chômage",
        "base": "brut",
        "valeurs": {"salarial": None, "patronal": rate},
        "meta": {
            "source": [{"url": URL_URSSAF, "label": "URSSAF – Taux employeur (secteur privé)", "date_doc": ""}],
            "generator": "scripts/assurancechomage/assurancechomage.py",
        },
    }

if __name__ == "__main__":
    taux = scrape_assurance_chomage()
    print(json.dumps(make_payload(taux), ensure_ascii=False))
    # code 0 si taux trouvé, sinon 2 (utile à l’orchestrateur)
    exit(0 if taux is not None else 2)
