projet/
├─ data/                       # vérité courante (consommée par l’app)
│  ├─ cotisations.json
│  ├─ pas.json
│  ├─ baremes_km.json
│  ├─ frais_pro.json
│  ├─ secu.json
│  ├─ metadata.json            # index global (dates, versions, hashes)
│  └─ .lock                    # verrou d’écriture (optionnel)
├─ staging/                    # sorties brutes des scrapers avant validation
│  ├─ cotisations.raw.json
│  ├─ pas.raw.json
│  ├─ baremes_km.raw.json
│  ├─ frais_pro.raw.json
│  └─ secu.raw.json
├─ schemas/                    # JSON Schema par fichier
│  ├─ cotisations.schema.json
│  ├─ pas.schema.json
│  ├─ baremes_km.schema.json
│  ├─ frais_pro.schema.json
│  └─ secu.schema.json
├─ sources/                    # provenance (snapshots HTML + empreintes)
│  ├─ html/
│  └─ manifests/
├─ scripts/
│  ├─ update_all.py            # pipeline: scrape → stage → validate → promote
│  ├─ AGIRC-ARRCO*.py
│  ├─ PAS*.py
│  ├─ bareme-indemnite-kilometrique*.py
│  └─ utils_common.py
├─ config/
│  ├─ sources_priority.json    # ordre de préférence des sources
│  └─ settings.json            # timeouts, UA, retries, logs
└─ logs/
   └─ updates.log
