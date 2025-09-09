# scripts/fraispro/fraispro_AI.py

import json
import os
import sys
from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup
from openai import OpenAI
from googlesearch import search
from dotenv import load_dotenv

load_dotenv()

SEARCH_QUERY = "barèmes frais professionnels URSSAF 2025"


# ---------- Utils ----------
def iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def extract_json_with_gpt(page_text: str, prompt: str) -> dict | None:
    if not os.getenv("OPENAI_API_KEY"):
        return None
    try:
        client = OpenAI()
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": "Tu es un extracteur de données qui répond uniquement en JSON valide."},
                {"role": "user", "content": prompt}
            ],
            temperature=0
        )
        extracted_text = response.choices[0].message.content.strip()
        return json.loads(extracted_text)
    except Exception as e:
        return None


# ---------- Normalisation ----------
def normalize_sections(sections: dict) -> dict:
    """
    Corrige les incohérences éventuelles pour coller au format attendu par l’orchestrateur.
    Exemple : grand_deplacement.metropole doit être une liste, pas un dict imbriqué.
    """
    gd = sections.get("grand_deplacement", {})

    # Normalisation de metropole : doit être une liste de périodes
    if isinstance(gd.get("metropole"), dict):
        repas = gd["metropole"].get("repas", {})
        logement = gd["metropole"].get("logement", {})
        sections["grand_deplacement"]["metropole"] = [
            {
                "periode_sejour": "3 premiers mois",
                "repas": repas.get("3_mois", 0),
                "logement_paris_banlieue": logement.get("paris", 0),
                "logement_province": logement.get("autres_departements", 0),
            },
            {
                "periode_sejour": "au-delà de 3 mois",
                "repas": repas.get("au_dela_3_mois", 0),
                "logement_paris_banlieue": logement.get("paris", 0),
                "logement_province": logement.get("autres_departements", 0),
            },
            {
                "periode_sejour": "au-delà de 24 mois",
                "repas": repas.get("au_dela_24_mois", 0),
                "logement_paris_banlieue": logement.get("paris", 0),
                "logement_province": logement.get("autres_departements", 0),
            },
        ]

    # Normalisation des groupes OM
    for grp in ("outre_mer_groupe1", "outre_mer_groupe2"):
        if isinstance(gd.get(grp), dict):
            val = gd[grp]
            sections["grand_deplacement"][grp] = [
                {"periode_sejour": "forfait", "hebergement": val.get("hebergement", 0), "repas": val.get("repas", 0)}
            ]

    return sections


# ---------- Core ----------
def get_fraispro_via_ai() -> dict | None:
    prompt_template = """
Analyse le texte suivant de la page URSSAF "Frais professionnels" pour 2025.
Extrait toutes les valeurs numériques pour remplir STRICTEMENT la structure JSON ci-dessous.

RÈGLES :
- Retourne un objet unique avec la clé racine "FRAIS_PROFESSIONNELS_2025".
- Garde toutes les clés, même si vides (mettre 0, [], ou objets vides).
- Aucun texte hors JSON.

Structure attendue :
{
  "id": "frais_pro",
  "type": "frais_professionnels",
  "libelle": "Frais professionnels (URSSAF)",
  "sections": {
    "repas": {
      "sur_lieu_travail": 0.0,
      "hors_locaux_sans_restaurant": 0.0,
      "hors_locaux_avec_restaurant": 0.0
    },
    "petit_deplacement": [
      {
        "km_min": 0,
        "km_max": 0,
        "montant": 0.0
      }
    ],
    "grand_deplacement": {
      "metropole": [
        {
          "periode_sejour": "texte",
          "repas": 0.0,
          "logement_paris_banlieue": 0.0,
          "logement_province": 0.0
        }
      ],
      "outre_mer_groupe1": [
        {
          "periode_sejour": "texte",
          "hebergement": 0.0,
          "repas": 0.0
        }
      ],
      "outre_mer_groupe2": [
        {
          "periode_sejour": "texte",
          "hebergement": 0.0,
          "repas": 0.0
        }
      ]
    },
    "mutation_professionnelle": {
      "hebergement_provisoire": {
        "montant_par_jour": 0.0
      },
      "hebergement_definitif": {
        "frais_installation": 0.0,
        "majoration_par_enfant": 0.0,
        "plafond_total": 0.0
      }
    },
    "mobilite_durable": {
      "employeurs_prives": {
        "limite_base": 0.0,
        "limite_cumul_transport_public": 0.0,
        "limite_cumul_carburant_total": 0.0,
        "limite_cumul_carburant_part_carburant": 0.0
      },
      "employeurs_publics": [
        {
          "jours_utilises": "texte",
          "montant_annuel": 0.0
        }
      ]
    },
    "teletravail": {
      "indemnite_sans_accord": {
        "par_jour": 0.0,
        "limite_mensuelle": 0.0,
        "par_mois_pour_1_jour_semaine": 0.0
      },
      "indemnite_avec_accord": {
        "par_jour": 0.0,
        "limite_mensuelle": 0.0,
        "par_mois_pour_1_jour_semaine": 0.0
      },
      "materiel_informatique_perso": {
        "montant_mensuel": 0.0
      }
    }
  },
  "meta": {
    "source": [
      {
        "url": "https://www.urssaf.fr/accueil/outils-documentation/taux-baremes/frais-professionnels.html",
        "label": "URSSAF — Frais professionnels",
        "date_doc": ""
      }
    ],
    "scraped_at": "2025-09-04T10:00:00Z",
    "generator": "scripts/fraispro/fraispro.py",
    "method": "primary"
  }
}

---
"""

    results = []
    try:
        results = list(search(SEARCH_QUERY, num_results=5, lang="fr"))
    except Exception as e:
        pass # ERREUR recherche Google

    if not results:
        return None

    for url in results:
        try:
            r = requests.get(url, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
            r.raise_for_status()
            soup = BeautifulSoup(r.text, "html.parser")
            page_text = soup.get_text(" ", strip=True)

            data = extract_json_with_gpt(page_text, prompt_template + page_text)
            if data and "FRAIS_PROFESSIONNELS_2025" in data:
                return normalize_sections(data["FRAIS_PROFESSIONNELS_2025"])
        except Exception as e:
            pass # ERREUR page

    return None


def build_payload(sections: dict) -> dict:
    return {
        "id": "frais_pro",
        "type": "frais_professionnels",
        "libelle": "Frais professionnels (IA)",
        "sections": sections,
        "meta": {
            "source": [
                {
                    "url": "https://www.urssaf.fr/accueil/outils-documentation/taux-baremes/frais-professionnels.html",
                    "label": "URSSAF — Frais professionnels 2025 (via IA)",
                    "date_doc": "",
                }
            ],
            "scraped_at": iso_now(),
            "generator": "scripts/fraispro/fraispro_AI.py",
            "method": "ai",
        },
    }


# ---------- Main ----------
if __name__ == "__main__":
    # La variable data_from_ai contient l'objet complet { "id": ..., "sections": {...} }
    data_from_ai = get_fraispro_via_ai()
    
    if data_from_ai:
        # On extrait UNIQUEMENT le dictionnaire de la clé "sections"
        sections_data = data_from_ai.get("sections", {})
        # On passe ce dictionnaire extrait à build_payload
        print(json.dumps(build_payload(sections_data), ensure_ascii=False))
    else:
        # En cas d'échec, on génère une structure vide correcte
        empty_sections = {
            "repas": {"sur_lieu_travail": 0, "hors_locaux_avec_restaurant": 0, "hors_locaux_sans_restaurant": 0},
            "petit_deplacement": [],
            "grand_deplacement": {"metropole": [], "outre_mer_groupe1": [], "outre_mer_groupe2": []},
            "mutation_professionnelle": {
                "hebergement_provisoire": {"montant_par_jour": 0},
                "hebergement_definitif": {"frais_installation": 0, "majoration_par_enfant": 0, "plafond_total": 0},
            },
            "mobilite_durable": {"employeurs_prives": {"limite_base": 0, "limite_cumul_transport_public": 0}},
            "teletravail": {"indemnite_sans_accord": {"par_jour": 0, "limite_mensuelle": 0, "par_mois_pour_1_jour_semaine": 0}},
        }
        print(json.dumps(build_payload(empty_sections), ensure_ascii=False))