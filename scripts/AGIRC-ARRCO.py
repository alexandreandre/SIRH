# scripts/AGIRC-ARRCO.py

import json
import re
import requests
from bs4 import BeautifulSoup

# --- Fichiers et URL cibles ---
FICHIER_TAUX = 'config/taux_cotisations.json'
URL_AGIRC_ARRCO = "https://www.agirc-arrco.fr/entreprises/mon-entreprise/calculer-et-declarer/le-calcul-des-cotisations-de-retraite-complementaire/"

# --------- Utils ---------
def _txt(el):
    return el.get_text(" ", strip=True).lower() if el else ""

def _has_pct(s: str) -> bool:
    return bool(re.search(r"\d+\s*,\s*\d+\s*%|\d+\s*%", s))

def parse_taux(text: str) -> float | None:
    """Nettoie un texte (ex: '3,15%') -> 0.0315."""
    if not text:
        return None
    try:
        cleaned_text = text.replace('\u202f', '').replace('\xa0', '')
        cleaned_text = cleaned_text.replace(',', '.').replace('%', '').strip()
        taux = float(cleaned_text) / 100.0
        return round(taux, 5)
    except (ValueError, AttributeError):
        return None

def _is_table_retraite(tbl) -> bool:
    # Souvent titrée "Taux de calcul des points" avec Tranche 1 / Tranche 2
    t = _txt(tbl)
    return ("taux de calcul des points" in t) and ("tranche 1" in t) and ("tranche 2" in t)

def _is_table_ceg(tbl) -> bool:
    # CEG sans CET
    t = _txt(tbl)
    return ("ceg" in t) and ("cet" not in t)

def _is_table_cet(tbl) -> bool:
    # CET sans CEG
    t = _txt(tbl)
    return ("cet" in t) and ("ceg" not in t)

def _is_table_apec(tbl) -> bool:
    # APEC est souvent libellé en dehors de la table. On combine indices.
    head = _txt(tbl.find("thead"))
    body = _txt(tbl.find("tbody"))
    if ("assiette tranche 1 + tranche 2" in head) and ("part salariale" in body) and ("part patronale" in body):
        return True
    # Fallback: label "APEC" juste au-dessus
    prev = tbl.find_previous(string=True)
    if prev and "apec" in prev.strip().lower():
        return True
    # Dernier filet de sécurité: 3 colonnes Part salariale / Part patronale / Total
    if ("part salariale" in body) and ("part patronale" in body) and ("total" in body):
        return True
    return False

# --------- Scraper principal ---------
def get_all_taux_agirc_arrco() -> dict | None:
    """Scrape la page web Agirc-Arrco pour extraire tous les taux."""
    try:
        print(f"Scraping de l'URL : {URL_AGIRC_ARRCO}...")
        response = requests.get(
            URL_AGIRC_ARRCO,
            timeout=20,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
        )
        response.raise_for_status()
        # lxml plus tolérant aux HTML réels
        soup = BeautifulSoup(response.text, "lxml")

        taux: dict[str, float] = {}
        all_tables = soup.find_all('table')
        print(f"DEBUG : {len(all_tables)} tables trouvées sur la page.")

        for i, table in enumerate(all_tables, start=1):
            print(f"\n--- Analyse de la table n°{i} ---")
            table_text = _txt(table)

            # --- Table des Taux de Retraite T1 et T2 ---
            if _is_table_retraite(table):
                print("DEBUG : Table Retraite (points) identifiée.")
                rows = table.find('tbody').find_all('tr')
                # On cherche lignes contenant "Tranche 1" et "Tranche 2" puis on lit la ligne suivante si besoin
                for r_idx, row in enumerate(rows):
                    row_txt = _txt(row)
                    if "tranche 1" in row_txt:
                        # ligne suivante ou même ligne selon structure
                        target = rows[r_idx + 1] if (r_idx + 1 < len(rows) and not _has_pct(row_txt)) else row
                        cells = target.find_all(['td', 'th'])
                        # On cherche deux pourcentages: salar + patronal
                        pcts = [parse_taux(c.get_text()) for c in cells if _has_pct(_txt(c))]
                        if len(pcts) >= 2:
                            taux['retraite_comp_t1_salarial'] = pcts[0]
                            taux['retraite_comp_t1_patronal'] = pcts[1]
                            print(f"  -> Retraite T1 (S: {pcts[0]}, P: {pcts[1]})")
                    if "tranche 2" in row_txt:
                        target = rows[r_idx + 1] if (r_idx + 1 < len(rows) and not _has_pct(row_txt)) else row
                        cells = target.find_all(['td', 'th'])
                        pcts = [parse_taux(c.get_text()) for c in cells if _has_pct(_txt(c))]
                        if len(pcts) >= 2:
                            taux['retraite_comp_t2_salarial'] = pcts[0]
                            taux['retraite_comp_t2_patronal'] = pcts[1]
                            print(f"  -> Retraite T2 (S: {pcts[0]}, P: {pcts[1]})")

            # --- Table des Taux CEG ---
            elif _is_table_ceg(table):
                print("DEBUG : Table CEG identifiée.")
                rows = table.find('tbody').find_all('tr')
                for r_idx, row in enumerate(rows):
                    row_txt = _txt(row)
                    if "tranche 1" in row_txt:
                        target = rows[r_idx + 1] if (r_idx + 1 < len(rows) and not _has_pct(row_txt)) else row
                        cells = target.find_all(['td', 'th'])
                        pcts = [parse_taux(c.get_text()) for c in cells if _has_pct(_txt(c))]
                        if len(pcts) >= 2:
                            taux['ceg_t1_salarial'] = pcts[0]
                            taux['ceg_t1_patronal'] = pcts[1]
                            print(f"  -> CEG T1 (S: {pcts[0]}, P: {pcts[1]})")
                    if "tranche 2" in row_txt:
                        target = rows[r_idx + 1] if (r_idx + 1 < len(rows) and not _has_pct(row_txt)) else row
                        cells = target.find_all(['td', 'th'])
                        pcts = [parse_taux(c.get_text()) for c in cells if _has_pct(_txt(c))]
                        if len(pcts) >= 2:
                            taux['ceg_t2_salarial'] = pcts[0]
                            taux['ceg_t2_patronal'] = pcts[1]
                            print(f"  -> CEG T2 (S: {pcts[0]}, P: {pcts[1]})")

            # --- Table du Taux CET ---
            elif _is_table_cet(table):
                print("DEBUG : Table CET identifiée.")
                # On prend la dernière ligne contenant des %
                rows = table.find('tbody').find_all('tr')
                data_cells = None
                for tr in rows[::-1]:
                    if _has_pct(_txt(tr)):
                        tds = tr.find_all(['td', 'th'])
                        if len(tds) >= 2:
                            data_cells = tds
                            break
                if data_cells:
                    # La plupart du temps: deux premières cellules = salariale, patronale
                    pcts = [parse_taux(c.get_text()) for c in data_cells if _has_pct(_txt(c))]
                    if len(pcts) >= 2:
                        taux['cet_salarial'] = pcts[0]
                        taux['cet_patronal'] = pcts[1]
                        print(f"  -> CET (S: {pcts[0]}, P: {pcts[1]})")

            # --- Table du Taux APEC ---
            elif _is_table_apec(table):
                print("DEBUG : Table APEC identifiée.")
                rows = table.find('tbody').find_all('tr')
                data_cells = None
                # Première ligne chiffrée avec des %
                for tr in rows:
                    if _has_pct(_txt(tr)):
                        tds = tr.find_all(['td', 'th'])
                        if len(tds) >= 2:
                            data_cells = tds
                            break
                if data_cells:
                    pcts = [parse_taux(c.get_text()) for c in data_cells if _has_pct(_txt(c))]
                    if len(pcts) >= 2:
                        taux['apec_salarial'] = pcts[0]
                        taux['apec_patronal'] = pcts[1]
                        print(f"  -> APEC (S: {pcts[0]}, P: {pcts[1]})")

        expected_keys_count = 12  # 6 lignes * 2 parts
        if len(taux) == expected_keys_count and all(v is not None for v in taux.values()):
            print(f"\n  - Tous les {len(taux)} taux Agirc-Arrco ont été extraits avec succès.")
            return taux
        else:
            raise ValueError(f"Certains taux sont manquants. Trouvés : {len(taux)}/{expected_keys_count}. Données: {taux}")

    except Exception as e:
        print(f"ERREUR lors du scraping : {e}")
        return None

def update_config_file(nouveaux_taux: dict):
    # inchangé
    try:
        with open(FICHIER_TAUX, 'r', encoding='utf-8') as f:
            config = json.load(f)

        retraite_t1 = config['TAUX_COTISATIONS']['retraite_comp_t1']
        retraite_t2 = config['TAUX_COTISATIONS']['retraite_comp_t2']
        ceg_t1 = config['TAUX_COTISATIONS']['ceg_t1']
        ceg_t2 = config['TAUX_COTISATIONS']['ceg_t2']
        cet = config['TAUX_COTISATIONS']['cet']
        apec = config['TAUX_COTISATIONS']['apec']

        print("\nMise à jour du fichier de configuration...")
        retraite_t1.update({'salarial': nouveaux_taux['retraite_comp_t1_salarial'], 'patronal': nouveaux_taux['retraite_comp_t1_patronal']})
        retraite_t2.update({'salarial': nouveaux_taux['retraite_comp_t2_salarial'], 'patronal': nouveaux_taux['retraite_comp_t2_patronal']})
        ceg_t1.update({'salarial': nouveaux_taux['ceg_t1_salarial'], 'patronal': nouveaux_taux['ceg_t1_patronal']})
        ceg_t2.update({'salarial': nouveaux_taux['ceg_t2_salarial'], 'patronal': nouveaux_taux['ceg_t2_patronal']})
        cet.update({'salarial': nouveaux_taux['cet_salarial'], 'patronal': nouveaux_taux['cet_patronal']})
        apec.update({'salarial': nouveaux_taux['apec_salarial'], 'patronal': nouveaux_taux['apec_patronal']})

        with open(FICHIER_TAUX, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)

        print(f"✅ Le fichier '{FICHIER_TAUX}' a été mis à jour avec succès.")
    except Exception as e:
        print(f"ERREUR : Une erreur est survenue lors de la mise à jour : {e}")

if __name__ == "__main__":
    extracted_taux = get_all_taux_agirc_arrco()
    if extracted_taux:
        update_config_file(extracted_taux)
