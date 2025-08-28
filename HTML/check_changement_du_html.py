#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Avant / Actuellement + décision terminale + surlignage fin.
- Compare LOCAL_FILE vs URL.
- Ouvre 2 iframes: Avant (local) / Actuellement (scrapé).
- Colore en ROUGE les deux côtés dès qu’un bloc diffère.
"""

import os, re, hashlib, requests, tempfile, webbrowser, html
from collections import Counter

# --------- Paramètres ----------
URL = "https://www.urssaf.fr/accueil/outils-documentation/taux-baremes/taux-cotisations-secteur-prive.html"
LOCAL_FILE = "HTML/page.html"
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
# -------------------------------

def fetch(url: str, timeout: int = 20) -> str:
    r = requests.get(url, timeout=timeout, headers={"User-Agent": UA})
    r.raise_for_status()
    r.encoding = r.apparent_encoding or r.encoding
    return r.text

def norm_html(s: str) -> str:
    s = re.sub(r">\s+<", "><", s)
    s = re.sub(r"\s{2,}", " ", s)
    return s.strip()

def sha(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8", "ignore")).hexdigest()

def ensure_parent(path: str):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)

# --------- Helpers HTML ----------
SCRIPT_TAG_RE = re.compile(r"(?is)<script\b[^>]*>.*?</script>")
SCRIPT_SELF_CLOSING_RE = re.compile(r"(?is)<script\b[^>]*/\s*>")
HEAD_RE = re.compile(r"(?is)<head\b[^>]*>(.*?)</head>")
BODY_RE = re.compile(r"(?is)<body\b[^>]*>(.*?)</body>")
LINK_STYLES_RE = re.compile(r'(?is)<link\b[^>]*rel=["\']stylesheet["\'][^>]*>')
STYLE_BLOCK_RE = re.compile(r"(?is)<style\b[^>]*>.*?</style>")
BASE_RE = re.compile(r'(?is)<base\b[^>]*href=["\']([^"\']+)["\']')

FINE_TAGS = ["td","th","li","p","span","strong","em","a","h1","h2","h3","h4","h5","h6"]
FALLBACK_TAGS = ["tr","div"]

def make_unit_regex(tags):
    pat = r"(?is)<(?P<tag>{})\b[^>]*>.*?</(?P=tag)>".format("|".join(tags))
    return re.compile(pat)

UNIT_RE_FINE = make_unit_regex(FINE_TAGS)
UNIT_RE_FALLBACK = make_unit_regex(FALLBACK_TAGS)

def strip_scripts(html_text: str) -> str:
    html_text = SCRIPT_TAG_RE.sub("", html_text)
    html_text = SCRIPT_SELF_CLOSING_RE.sub("", html_text)
    return html_text

def extract_head_html(src_html: str) -> str:
    m = HEAD_RE.search(src_html)
    return m.group(1) if m else ""

def extract_body_html(src_html: str) -> str:
    m = BODY_RE.search(src_html)
    if m: return m.group(1)
    return src_html

def head_to_css_head(head_inner: str, base_href: str) -> str:
    head_inner = strip_scripts(head_inner)
    links = LINK_STYLES_RE.findall(head_inner)
    styles = STYLE_BLOCK_RE.findall(head_inner)
    parts = [f'<base href="{html.escape(base_href, quote=True)}">'] + links + styles
    parts.append("""<style>
      .wm{position:fixed;top:8px;right:12px;padding:4px 8px;background:#111A;color:#fff;font:600 12px/1.2 ui-sans-serif;z-index:9999;border-radius:6px}
      .chg{color:#c00 !important}
    </style>""")
    return "\n".join(parts)

def doc_for_iframe(head_css: str, body_inner: str, watermark: str) -> str:
    body_inner = strip_scripts(body_inner)
    return f"""<!doctype html><html><head><meta charset="utf-8">{head_css}</head>
<body><div class="wm">{html.escape(watermark)}</div>{body_inner}</body></html>"""

def visible_text_only(html_fragment: str) -> str:
    txt = re.sub(r"(?is)<style\b[^>]*>.*?</style>", " ", html_fragment)
    txt = re.sub(r"(?is)<[^>]+>", " ", txt)
    txt = html.unescape(txt)
    txt = re.sub(r"\s+", " ", txt)
    return txt.strip().lower()

def find_units(html_text: str, fine=True):
    rx = UNIT_RE_FINE if fine else UNIT_RE_FALLBACK
    units = []
    for m in rx.finditer(html_text):
        seg = m.group(0)
        key = visible_text_only(seg)
        units.append({
            "start": m.start(),
            "end": m.end(),
            "tag": m.group("tag").lower(),
            "html": seg,
            "key": key,
        })
    return units

def add_red_style(opening_tag_html: str) -> str:
    m = re.match(r'(?is)^<(?P<tag>\w+)(?P<attrs>[^>]*)>', opening_tag_html)
    if not m:
        return opening_tag_html
    tag, attrs = m.group("tag"), m.group("attrs")
    if re.search(r'(?i)\bstyle\s*=', attrs):
        attrs = re.sub(r'(?is)\bstyle\s*=\s*([\'"])(.*?)\1',
                       lambda mm: f'style="{mm.group(2).rstrip(";")}; color:#c00 !important"',
                       attrs, count=1)
    else:
        attrs = attrs + ' style="color:#c00 !important"'
    return f"<{tag}{attrs}>"

def highlight_whole_units(html_text: str, which_indices: set, rx):
    if not which_indices:
        return html_text
    out = []
    cursor = 0
    for idx, m in enumerate(rx.finditer(html_text)):
        start, end = m.start(), m.end()
        out.append(html_text[cursor:start])
        seg = m.group(0)
        if idx in which_indices:
            open_tag_match = re.match(r'(?is)^<\w+[^>]*>', seg)
            if open_tag_match:
                open_tag = open_tag_match.group(0)
                seg = add_red_style(open_tag) + seg[open_tag_match.end():]
        out.append(seg)
        cursor = end
    out.append(html_text[cursor:])
    return "".join(out)

def decide_units_to_highlight(local_units, remote_units):
    c_local = Counter(u["key"] for u in local_units)
    c_remote = Counter(u["key"] for u in remote_units)

    surplus_local = {k: max(0, c_local[k] - c_remote.get(k, 0)) for k in c_local}
    surplus_remote = {k: max(0, c_remote[k] - c_local.get(k, 0)) for k in c_remote}

    mark_local, mark_remote = set(), set()

    rem = surplus_local.copy()
    for i, u in enumerate(local_units):
        k = u["key"]
        if rem.get(k, 0) > 0:
            mark_local.add(i)
            rem[k] -= 1

    rem = surplus_remote.copy()
    for i, u in enumerate(remote_units):
        k = u["key"]
        if rem.get(k, 0) > 0:
            mark_remote.add(i)
            rem[k] -= 1

    # --- Ajout: si un côté a marqué, marquer aussi l’autre côté sur le même "key" ---
    keys_local = {local_units[i]["key"] for i in mark_local}
    keys_remote = {remote_units[i]["key"] for i in mark_remote}
    all_diff_keys = keys_local | keys_remote

    for i, u in enumerate(local_units):
        if u["key"] in all_diff_keys:
            mark_local.add(i)
    for i, u in enumerate(remote_units):
        if u["key"] in all_diff_keys:
            mark_remote.add(i)

    return mark_local, mark_remote

def mark_changes_finely(body_local, body_remote):
    local_u_f = find_units(body_local, fine=True)
    remote_u_f = find_units(body_remote, fine=True)
    mark_loc, mark_rem = decide_units_to_highlight(local_u_f, remote_u_f)

    if mark_loc or mark_rem:
        body_local_marked  = highlight_whole_units(body_local,  mark_loc, UNIT_RE_FINE)
        body_remote_marked = highlight_whole_units(body_remote, mark_rem, UNIT_RE_FINE)
        return body_local_marked, body_remote_marked

    # fallback
    local_u_b = find_units(body_local, fine=False)
    remote_u_b = find_units(body_remote, fine=False)
    mark_loc_b, mark_rem_b = decide_units_to_highlight(local_u_b, remote_u_b)

    body_local_marked  = highlight_whole_units(body_local,  mark_loc_b, UNIT_RE_FALLBACK)
    body_remote_marked = highlight_whole_units(body_remote, mark_rem_b, UNIT_RE_FALLBACK)
    return body_local_marked, body_remote_marked

def build_report_page(left_src: str, right_src: str, local_sha: str, remote_sha: str, local_path: str, url: str) -> str:
    return f"""<!doctype html>
<html lang="fr"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Avant / Actuellement</title>
<style>
  :root {{ --bg:#0f172a; --fg:#e2e8f0; --mut:#94a3b8; }}
  * {{ box-sizing:border-box }}
  body {{ margin:0; background:var(--bg); color:var(--fg); font-family:ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto }}
  header {{ padding:12px 16px; border-bottom:1px solid #233; display:flex; gap:12px; flex-wrap:wrap; align-items:center }}
  .badge {{ font-size:12px; background:#1e293b; color:#cbd5e1; border-radius:999px; padding:2px 8px }}
  .grid {{ display:grid; grid-template-columns:1fr 1fr; gap:0 }}
  .col {{ display:flex; flex-direction:column; min-height:calc(100vh - 64px) }}
  .col h3 {{ margin:0; padding:10px 12px; background:#13203f; color:#cbd5e1; border-bottom:1px solid #1e293b }}
  iframe {{ flex:1; width:100%; border:0; background:white }}
  a {{ color:#a5b4fc; text-decoration:none }}
  a:hover {{ text-decoration:underline }}
</style>
</head>
<body>
<header>
  <strong>Avant / Actuellement</strong>
  <span class="badge">Local SHA {html.escape(local_sha)}</span>
  <span class="badge">Remote SHA {html.escape(remote_sha)}</span>
  <span class="badge">Local: {html.escape(local_path)}</span>
  <a class="badge" href="{html.escape(url)}" target="_blank">Ouvrir l’URL distante</a>
</header>
<div class="grid">
  <div class="col">
    <h3>Avant (fichier local)</h3>
    <iframe src="{left_src}" sandbox="allow-same-origin"></iframe>
  </div>
  <div class="col">
    <h3>Actuellement (scrapé)</h3>
    <iframe src="{right_src}" sandbox="allow-same-origin"></iframe>
  </div>
</div>
</body></html>"""

def main():
    try:
        remote_raw = fetch(URL)
    except Exception as e:
        print(f"Erreur réseau: {e}")
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

    alt = os.path.splitext(LOCAL_FILE)[0] + ".remote.html"
    with open(alt, "w", encoding="utf-8") as f:
        f.write(remote_raw)
    print(f"Changements détectés. Nouvelle version enregistrée: {alt}")

    # HEAD/CSS
    local_head  = extract_head_html(local_raw)
    remote_head = extract_head_html(remote_raw)
    base_local  = BASE_RE.search(local_head or "").group(1) if BASE_RE.search(local_head or "") else URL
    base_remote = BASE_RE.search(remote_head or "").group(1) if BASE_RE.search(remote_head or "") else URL
    head_css_local  = head_to_css_head(local_head,  base_local)
    head_css_remote = head_to_css_head(remote_head, base_remote)

    body_local  = extract_body_html(local_raw)
    body_remote = extract_body_html(remote_raw)

    body_local_marked, body_remote_marked = mark_changes_finely(body_local, body_remote)

    doc_avant = doc_for_iframe(head_css_local,  body_local_marked,  "AVANT")
    doc_now   = doc_for_iframe(head_css_remote, body_remote_marked, "ACTUEL")

    tmpdir = tempfile.mkdtemp(prefix="html_before_after_")
    avant_html_path = os.path.join(tmpdir, "avant_iframe.html")
    actuel_html_path = os.path.join(tmpdir, "actuel_iframe.html")
    with open(avant_html_path, "w", encoding="utf-8") as f:
        f.write(doc_avant)
    with open(actuel_html_path, "w", encoding="utf-8") as f:
        f.write(doc_now)

    left_src  = "file://" + avant_html_path
    right_src = "file://" + actuel_html_path

    report_html = build_report_page(left_src, right_src, local_sha, remote_sha, os.path.abspath(LOCAL_FILE), URL)
    report_path = os.path.join(tmpdir, "rapport.html")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report_html)
    print(f"Rapport: {report_path}")
    webbrowser.open("file://" + report_path)

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
