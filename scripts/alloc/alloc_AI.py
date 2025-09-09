# scripts/alloc/alloc_AI.py

import json
import os
import re
import time
import requests
from bs4 import BeautifulSoup
from googlesearch import search
from openai import OpenAI
from dotenv import load_dotenv
from typing import Optional, Dict, Any, List, Tuple

load_dotenv()

SEARCH_QUERIES = [
    "site:urssaf.fr allocations familiales taux plein taux réduit actuel",
    "site:urssaf.fr Taux de cotisations employeur allocations familiales actuel",
    "allocations familiales taux réduit 3,5 SMIC actuel urssaf",
    "site:service-public.fr allocations familiales cotisations taux plein réduit actuel",
    "taux cotisation allocations familiales actuel urssaf plein réduit",
]
FALLBACK_URLS = [
    "https://www.urssaf.fr/accueil/outils-documentation/taux-baremes/taux-cotisations-secteur-prive.html",
]

def ask_ai_for_both(page_text: str) -> Optional[Dict[str, Any]]:
    """
    Demande à l'IA d'extraire les 2 taux (plein et réduit) en POURCENT (ex: 3.45).
    Renvoie {"plein": float|None, "reduit": float|None} ou None en cas d'échec.
    """
    if not os.getenv("OPENAI_API_KEY"):
        return None
    try:
        client = OpenAI()
        prompt = (
            "Tu extrais UNIQUEMENT les DEUX taux patronaux d'allocations familiales (France) depuis ce texte :\n"
            '- "taux plein" (aussi appelé "droit commun")\n'
            '- "taux réduit" (salaires ≤ 3,5 SMIC)\n\n'
            "Réponds STRICTEMENT en JSON:\n"
            "{\n"
            '  "plein": ...,\n'
            '  "reduit": ...\n'
            "}\n\n"
            "Les valeurs sont en POURCENT (nombre, pas de texte, pas le symbole %). Si introuvable, mets null.\n"
            "Ne fournis AUCUN autre texte que le JSON.\n"
            "Texte:\n---\n"
            + page_text[:12000]
        )
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": "Assistant d'extraction de données, sortie JSON stricte."},
                {"role": "user", "content": prompt},
            ],
            temperature=0,
        )
        raw = resp.choices[0].message.content.strip()
        data = json.loads(raw)
        return {"plein": data.get("plein"), "reduit": data.get("reduit")}
    except Exception:
        return None

def to_rate(v) -> Optional[float]:
    """Convertit un pourcentage (ex: 3.45) en taux réel (0.0345)."""
    if v is None:
        return None
    try:
        return round(float(v) / 100.0, 6)
    except Exception:
        return None

def prioritize_urls(urls: List[str]) -> List[str]:
    """Priorise urssaf.fr puis service-public.fr puis le reste."""
    seen = set()
    def dedup(seq):
        out = []
        for u in seq:
            if u not in seen:
                seen.add(u)
                out.append(u)
        return out
    urssaf = dedup([u for u in urls if "urssaf.fr" in u])
    sp = dedup([u for u in urls if "service-public.fr" in u])
    others = dedup([u for u in urls if "urssaf.fr" not in u and "service-public.fr" not in u])
    return urssaf + sp + others

def fetch_text(url: str) -> Optional[str]:
    try:
        r = requests.get(url, timeout=25, headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        txt = soup.get_text(" ", strip=True)
        txt = re.sub(r"\s+", " ", txt)
        return txt if txt else None
    except Exception:
        return None

def merge_partial(current: Tuple[Optional[float], Optional[float]], new: Tuple[Optional[float], Optional[float]]) -> Tuple[Optional[float], Optional[float]]:
    p_cur, r_cur = current
    p_new, r_new = new
    return (p_cur if p_cur is not None else p_new, r_cur if r_cur is not None else r_new)

def run() -> Dict[str, Any]:
    sources = []
    plein: Optional[float] = None
    reduit: Optional[float] = None

    # Stratégie: plusieurs vagues de recherches + URLs de secours, jusqu'à obtenir les 2 valeurs
    rounds = 3
    for round_idx in range(rounds):
        # 1) Requêtes Google variées
        for query in SEARCH_QUERIES:
            try:
                urls = list(search(query, num_results=40, lang="fr"))
            except Exception:
                urls = []
            for url in prioritize_urls(urls):
                # Si on a déjà les deux, stop
                if plein is not None and reduit is not None:
                    break
                txt = fetch_text(url)
                if not txt:
                    continue
                got = ask_ai_for_both(txt)
                if not got:
                    continue
                p = to_rate(got.get("plein"))
                rdt = to_rate(got.get("reduit"))
                # On accepte les progrès partiels et on continue
                before = (plein, reduit)
                plein, reduit = merge_partial(before, (p, rdt))
                if (p is not None) or (rdt is not None):
                    sources.append({"url": url, "label": "Source détectée par IA", "date_doc": ""})
            if plein is not None and reduit is not None:
                break
        if plein is not None and reduit is not None:
            break

        # 2) URLs de secours connues (URSSAF)
        for url in FALLBACK_URLS:
            if plein is not None and reduit is not None:
                break
            txt = fetch_text(url)
            if not txt:
                continue
            got = ask_ai_for_both(txt)
            if not got:
                continue
            p = to_rate(got.get("plein"))
            rdt = to_rate(got.get("reduit"))
            before = (plein, reduit)
            plein, reduit = merge_partial(before, (p, rdt))
            if (p is not None) or (rdt is not None):
                sources.append({"url": url, "label": "Source de secours (URSSAF)", "date_doc": ""})

        # Petite pause avant un nouveau tour si nécessaire
        if plein is None or reduit is None:
            time.sleep(1.0)

    return {
        "id": "allocations_familiales",
        "type": "cotisation",
        "libelle": "Allocations familiales",
        "base": "brut",
        "valeurs": {
            "salarial": None,
            "patronal_plein": plein,
            "patronal_reduit": reduit,
        },
        "meta": {
            "source": sources,
            "generator": "scripts/alloc/alloc_AI.py",
        },
    }

if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False))
