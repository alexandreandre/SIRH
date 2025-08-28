#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Avant / Actuellement + décision terminale + clic Playwright robuste + surlignage fin.
- Ouvre la page, clique l’onglet "Taux de cotisations salarié" (ARIA role=tab), récupère le HTML.
- Compare au LOCAL_FILE, affiche 2 iframes, colore en rouge les plus petits conteneurs textuels modifiés.
- Demande si remplacement du fichier local.
"""

import os, re, hashlib, tempfile, webbrowser, html
from collections import Counter
from playwright.sync_api import sync_playwright

# --------- Paramètres ----------
URL = "https://www.urssaf.fr/accueil/outils-documentation/taux-baremes/taux-cotisations-secteur-prive.html"
LOCAL_FILE = "HTML/page.html"
# -------------------------------

# ---------- Playwright: fetch après clic ----------
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")

def fetch_with_click(url: str) -> str:
    def try_once(browser_type):
        browser = browser_type.launch(headless=True, args=[
            "--disable-dev-shm-usage",
            "--no-sandbox",
            "--disable-web-security",
            "--disable-features=IsolateOrigins,site-per-process",
        ])
        ctx = browser.new_context(
            user_agent=UA,
            locale="fr-FR",
            timezone_id="Europe/Paris",
            ignore_https_errors=True,
            java_script_enabled=True,
            viewport={"width": 1400, "height": 900},
            extra_http_headers={
                "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
                "Cache-Control": "no-cache",
            },
        )
        page = ctx.new_page()

        # Bloque polices/analytics pour limiter le bruit réseaux
        page.route("**/*", lambda route: route.abort() if any(
            k in route.request.url.lower() for k in (".woff", ".woff2", "fonts.googleapis", "googletagmanager", "analytics")
        ) else route.continue_())

        page.goto(url, timeout=90000, wait_until="domcontentloaded")
        try:
            page.wait_for_load_state("networkidle", timeout=30000)
        except Exception:
            pass

        tab = page.get_by_role("tab", name="Taux de cotisations salarié")
        tab.wait_for(state="visible", timeout=20000)
        tab.click(timeout=20000)

        # Attente raisonnable que l’onglet devienne actif et que le contenu se stabilise
        try:
            page.wait_for_function("""(name)=>{
              const t=[...document.querySelectorAll('[role="tab"]')].find(x=>x.innerText.trim().includes(name));
              return t && (t.getAttribute('aria-selected')==='true');
            }""", arg="Taux de cotisations salarié", timeout=15000)
        except Exception:
            pass
        try:
            page.wait_for_load_state("networkidle", timeout=15000)
        except Exception:
            pass
        page.wait_for_timeout(1000)

        content = page.content()
        ctx.close()
        browser.close()
        return content

    with sync_playwright() as p:
        errors = []
        for engine in (p.chromium, p.webkit, p.firefox):
            for _ in range(2):
                try:
                    return try_once(engine)
                except Exception as e:
                    errors.append(str(e))
                    continue
        raise RuntimeError("Playwright échec après tentatives. Détails: " + " | ".join(errors[:3]))

# ---------- Normalisation / utilitaires ----------
def norm_html(s: str) -> str:
    s = re.sub(r">\s+<", "><", s)
    s = re.sub(r"\s{2,}", " ", s)
    return s.strip()

def sha(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8", "ignore")).hexdigest()

def ensure_parent(path: str):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)

# ---------- Parsing HTML léger ----------
SCRIPT_TAG_RE = re.compile(r"(?is)<script\b[^>]*>.*?</script>")
HEAD_RE = re.compile(r"(?is)<head\b[^>]*>(.*?)</head>")
BODY_RE = re.compile(r"(?is)<body\b[^>]*>(.*?)</body>")
BASE_RE = re.compile(r'(?is)<base\b[^>]*href=["\']([^"\']+)["\']')

FINE_TAGS = ["td","th","li","p","span","strong","em","a","h1","h2","h3","h4","h5","h6"]
FALLBACK_TAGS = ["tr","div"]

def make_unit_regex(tags):
    return re.compile(r"(?is)<(?P<tag>{})\b[^>]*>.*?</(?P=tag)>".format("|".join(tags)))

UNIT_RE_FINE = make_unit_regex(FINE_TAGS)
UNIT_RE_FALLBACK = make_unit_regex(FALLBACK_TAGS)

def strip_scripts(html_text: str) -> str:
    return SCRIPT_TAG_RE.sub("", html_text)

def extract_head_html(src_html: str) -> str:
    m = HEAD_RE.search(src_html)
    return m.group(1) if m else ""

def extract_body_html(src_html: str) -> str:
    m = BODY_RE.search(src_html)
    return m.group(1) if m else src_html

def head_to_css_head(head_inner: str, base_href: str) -> str:
    links = re.findall(r'(?is)<link\b[^>]*rel=["\']stylesheet["\'][^>]*>', strip_scripts(head_inner))
    styles = re.findall(r"(?is)<style\b[^>]*>.*?</style>", head_inner)
    parts = [f'<base href="{html.escape(base_href, quote=True)}">'] + links + styles
    parts.append("""<style>
      .wm{position:fixed;top:8px;right:12px;padding:4px 8px;background:#111A;color:#fff;font:600 12px/1.2 ui-sans-serif;z-index:9999;border-radius:6px}
      .chg{color:#c00 !important}
    </style>""")
    return "\n".join(parts)

def doc_for_iframe(head_css: str, body_inner: str, watermark: str) -> str:
    return f"""<!doctype html><html><head><meta charset="utf-8">{head_css}</head>
<body><div class="wm">{html.escape(watermark)}</div>{strip_scripts(body_inner)}</body></html>"""

def visible_text_only(html_fragment: str) -> str:
    txt = re.sub(r"(?is)<style\b[^>]*>.*?</style>", " ", html_fragment)
    txt = re.sub(r"(?is)<[^>]+>", " ", txt)
    return html.unescape(txt).strip().lower()

def find_units(html_text: str, fine=True):
    rx = UNIT_RE_FINE if fine else UNIT_RE_FALLBACK
    return [{"html": m.group(0), "key": visible_text_only(m.group(0))} for m in rx.finditer(html_text)]

def add_red_style(seg: str) -> str:
    return re.sub(r'(?is)^<(\w+)([^>]*)>', r'<\1\2 style="color:#c00 !important">', seg, 1)

def highlight_units(html_text: str, indices: set, rx):
    out, cursor = [], 0
    for idx, m in enumerate(rx.finditer(html_text)):
        out.append(html_text[cursor:m.start()])
        seg = m.group(0)
        if idx in indices:
            seg = add_red_style(seg)
        out.append(seg)
        cursor = m.end()
    out.append(html_text[cursor:])
    return "".join(out)

def decide_units(local_units, remote_units):
    c_local = Counter(u["key"] for u in local_units)
    c_remote = Counter(u["key"] for u in remote_units)
    diff_keys = {k for k in c_local if c_local[k]!=c_remote.get(k,0)} | {k for k in c_remote if c_remote[k]!=c_local.get(k,0)}
    mark_local = {i for i,u in enumerate(local_units) if u["key"] in diff_keys}
    mark_remote = {i for i,u in enumerate(remote_units) if u["key"] in diff_keys}
    return mark_local, mark_remote

def mark_changes(body_local, body_remote):
    local_u, remote_u = find_units(body_local), find_units(body_remote)
    mark_loc, mark_rem = decide_units(local_u, remote_u)
    if mark_loc or mark_rem:
        return (highlight_units(body_local, mark_loc, UNIT_RE_FINE),
                highlight_units(body_remote, mark_rem, UNIT_RE_FINE))
    # fallback
    local_u, remote_u = find_units(body_local, fine=False), find_units(body_remote, fine=False)
    mark_loc, mark_rem = decide_units(local_u, remote_u)
    return (highlight_units(body_local, mark_loc, UNIT_RE_FALLBACK),
            highlight_units(body_remote, mark_rem, UNIT_RE_FALLBACK))

def build_report(left_src, right_src, local_sha, remote_sha, local_path, url):
    return f"""<!doctype html>
<html><head><meta charset="utf-8"><title>Avant / Actuellement</title>
<style>
  body{{margin:0;font-family:sans-serif;background:#0f172a;color:#e2e8f0}}
  header{{padding:10px;background:#13203f;color:#cbd5e1}}
  iframe{{width:50%;height:90vh;border:0;float:left}}
  .meta{{font-size:12px;opacity:.8}}
</style></head>
<body>
<header>
  Avant vs Actuellement
  <div class="meta">Local SHA {local_sha} | Remote SHA {remote_sha} | Local: {html.escape(local_path)} | <a href="{html.escape(url)}" style="color:#a5b4fc" target="_blank">ouvrir l’URL</a></div>
</header>
<iframe src="{left_src}"></iframe><iframe src="{right_src}"></iframe>
</body></html>"""

# ---------- Main ----------
def main():
    try:
        remote_raw = fetch_with_click(URL)
    except Exception as e:
        print(f"Erreur Playwright: {e}")
        return

    ensure_parent(LOCAL_FILE)

    if not os.path.exists(LOCAL_FILE):
        with open(LOCAL_FILE, "w", encoding="utf-8") as f:
            f.write(remote_raw)
        print(f"Créé: {LOCAL_FILE} (SHA {sha(norm_html(remote_raw))[:12]})")
        return

    with open(LOCAL_FILE, "r", encoding="utf-8", errors="ignore") as f:
        local_raw = f.read()

    local_sha  = sha(norm_html(local_raw))[:12]
    remote_sha = sha(norm_html(remote_raw))[:12]

    if local_sha == remote_sha:
        print(f"Aucun changement. SHA {remote_sha}")
        return

    print("Changements détectés.")

    # Corps + surlignage fin (deux côtés)
    body_local  = extract_body_html(local_raw)
    body_remote = extract_body_html(remote_raw)
    local_marked, remote_marked = mark_changes(body_local, body_remote)

    # Head/CSS
    local_head  = extract_head_html(local_raw)
    remote_head = extract_head_html(remote_raw)
    base_local  = (BASE_RE.search(local_head or "").group(1) if BASE_RE.search(local_head or "") else URL)
    base_remote = (BASE_RE.search(remote_head or "").group(1) if BASE_RE.search(remote_head or "") else URL)
    head_css_local  = head_to_css_head(local_head,  base_local)
    head_css_remote = head_to_css_head(remote_head, base_remote)

    # Iframes
    doc_avant = doc_for_iframe(head_css_local,  local_marked,  "AVANT")
    doc_now   = doc_for_iframe(head_css_remote, remote_marked, "ACTUEL")

    tmpdir = tempfile.mkdtemp(prefix="html_diff_")
    avant_path  = os.path.join(tmpdir, "avant.html")
    actuel_path = os.path.join(tmpdir, "actuel.html")
    with open(avant_path,  "w", encoding="utf-8") as f: f.write(doc_avant)
    with open(actuel_path, "w", encoding="utf-8") as f: f.write(doc_now)

    report = build_report("file://"+avant_path, "file://"+actuel_path, local_sha, remote_sha, os.path.abspath(LOCAL_FILE), URL)
    report_path = os.path.join(tmpdir, "rapport.html")
    with open(report_path, "w", encoding="utf-8") as f: f.write(report)
    print(f"Rapport: {report_path}")
    webbrowser.open("file://" + report_path)

    # Décision
    while True:
        ans = input("Remplacer le fichier local par la version actuelle ? [y/N] ").strip().lower()
        if ans in ("y","yes","o","oui"):
            with open(LOCAL_FILE, "w", encoding="utf-8") as f:
                f.write(remote_raw)
            print(f"Remplacé: {LOCAL_FILE}")
            break
        if ans in ("n","no","non",""):
            print("Conservé. Aucune modification du fichier local.")
            break
        print("Réponse invalide. Tapez 'y' ou 'n'.")

if __name__ == "__main__":
    main()
