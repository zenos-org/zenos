#!/usr/bin/env python3
"""Generate the ZENOS feature pages (English and Japanese) into site/.
Usage: python3 build.py SITE_DIR"""
import html, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import data_en as EN
import data_ja as JA

E = html.escape
TAGCLS = {"Working today": "t-ok", "Tested": "t-ok", "Proved in Lean 4": "t-acc", "Testing": "t-warn", "Next release": "t-grey", "Trusted, not proved": "t-warn"}
ROWCLS = ["Stop the PC", "PC を止める", "Red", "赤"]


def tagname(t, lang):
    return JA.TAGS.get(t, t) if lang == "ja" else t


def tag(t, lang):
    return f'<span class="tag {TAGCLS.get(t, "t-acc")}">{E(tagname(t, lang))}</span>'


def nav(ui, here_other):
    links = "".join(f'<a href="{h}"{" aria-current=\"page\"" if "features" in h else ""}>{E(n)}</a>' for n, h in ui["nav"])
    home = "/ja/" if ui["lang"] == "ja" else "/"
    return (f'<nav id="nav"><div class="wrap"><a class="logo" href="{home}"><img src="/img/logo.svg" alt="">ZENOS</a>'
            f'<div class="links">{links}<a class="lang" href="{here_other}" hreflang="{"en" if ui["lang"] == "ja" else "ja"}">{E(ui["other"][0])}</a></div>'
            f'<a class="btn navgh" href="https://github.com/zenos-org/zenos">{E(ui["gh"])}</a>'
            '<button class="menu" id="menu" aria-label="Menu" aria-expanded="false">☰</button></div></nav>')


def head(ui, title, desc, path, alt):
    return f'''<!doctype html>
<html lang="{ui["lang"]}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{E(title)}</title>
<meta name="description" content="{E(desc)}">
<meta property="og:title" content="{E(title)}">
<meta property="og:description" content="{E(desc)}">
<meta property="og:image" content="https://zenos-os.org/img/desktop.png">
<meta property="og:url" content="https://zenos-os.org{path}">
<meta name="twitter:card" content="summary_large_image">
<link rel="alternate" hreflang="en" href="https://zenos-os.org{alt[0]}">
<link rel="alternate" hreflang="ja" href="https://zenos-os.org{alt[1]}">
<link rel="icon" href="/img/logo.svg">
<link rel="stylesheet" href="/features.css">
</head>
<body class="lang-{ui["lang"]}">
'''


SCRIPT = '''<script>
const n=document.getElementById('nav'),m=document.getElementById('menu');
m.addEventListener('click',()=>{const o=n.classList.toggle('open');m.setAttribute('aria-expanded',o)});
</script>
</body>
</html>
'''


def footer(ui):
    return f'<footer><div class="wrap">{ui["footer"]}</div></footer>'


def bullets(items):
    if not items:
        return ""
    return '<ul class="dots">' + "".join(f"<li>{E(i)}</li>" for i in items) + "</ul>"


def page(M, slug, lang):
    ui, d = M.UI, M.P[slug]
    base = "/ja/features/" if lang == "ja" else "/features/"
    path = base + slug + "/"
    alt = ("/features/" + slug + "/", "/ja/features/" + slug + "/")
    other = alt[0] if lang == "ja" else alt[1]
    i = EN.ORDER.index(slug)
    nxt = EN.ORDER[(i + 1) % len(EN.ORDER)]
    out = [head(ui, f'{d["name"]} — ZENOS', d["lead"], path, alt), nav(ui, other), '<main>']
    out.append('<section class="hero"><div class="wrap">')
    out.append(f'<p class="crumb"><a href="{base}">{E(ui["features"])}</a> / {E(d["name"])}</p>')
    out.append('<div class="tags">' + "".join(tag(t, lang) for t in d["tags"]) + '</div>')
    out.append(f'<h1>{E(d["h1"])}</h1><p class="lead">{E(d["lead"])}</p>')
    out.append('<div class="grid g3 stats">' + "".join(f'<div class="card"><b>{E(a)}</b><p>{E(b)}</p></div>' for a, b in d["stats"]) + '</div>')
    out.append('</div></section>')
    out.append(f'<section><div class="wrap"><p class="eyebrow">{E(ui["how"])}</p><h2>{E(d["howTitle"])}</h2><div class="grid g3">')
    for k, (h, p, b) in enumerate(d["how"], 1):
        out.append(f'<div class="card step"><span class="num">{k}</span><h3>{E(h)}</h3><p>{E(p)}</p>{bullets(b)}</div>')
    out.append('</div></div></section>')
    if d.get("table"):
        t = d["table"]
        out.append(f'<section><div class="wrap"><p class="eyebrow">{E(t["eyebrow"])}</p><h2>{E(t["title"])}</h2><div class="card table">')
        for a, b in t["rows"]:
            cls = "t-warn" if b in ROWCLS else "t-acc"
            out.append(f'<div class="row"><span>{E(a)}</span><span class="tag {cls}">{E(b)}</span></div>')
        out.append('</div>')
        if t.get("note"):
            out.append(f'<p class="note">{E(t["note"])}</p>')
        out.append('</div></section>')
    if d.get("extra"):
        x = d["extra"]
        out.append(f'<section class="tight"><div class="wrap"><div class="card moment"><p class="eyebrow">{E(x["eyebrow"])}</p><p>{E(x["text"])}</p></div></div></section>')
    left_tag = d.get("leftTag", "Proved in Lean 4")
    left_title = d.get("leftTitle") or ui["provedTitle"]
    if lang == "ja" and d.get("leftTitle") is None:
        left_title = ui["provedTitle"]
    out.append(f'<section><div class="wrap"><p class="eyebrow">{E(ui["proven"])}</p><h2>{E(d["provenTitle"])}</h2><div class="grid g2">')
    out.append(f'<div class="card">{tag(left_tag, lang)}<h3>{E(left_title)}</h3>{bullets(d["proven"])}</div>')
    out.append(f'<div class="card">{tag("Trusted, not proved", lang)}<h3>{E(ui["trustedTitle"])}</h3>{bullets(d["trusted"])}</div>')
    out.append('</div></div></section>')
    if d.get("tryit"):
        out.append(f'<section><div class="wrap"><p class="eyebrow">{E(ui["tryit"])}</p><h2>{E(ui["tryTitle"])}</h2><div class="grid g3">')
        for k, (h, p) in enumerate(d["tryit"], 1):
            out.append(f'<div class="card"><span class="big">{k}</span><h3>{E(h)}</h3><p>{E(p)}</p></div>')
        out.append('</div></div></section>')
    out.append('<section class="tight"><div class="wrap"><div class="ctas">')
    for k, (l, h) in enumerate(d["links"]):
        out.append(f'<a class="btn{" p" if k == 0 else ""}" href="{h}">{E(l)}</a>')
    out.append('</div>')
    out.append(f'<div class="pager"><a href="{base}">{E(ui["all"])}</a><a class="nx" href="{base}{nxt}/">{E(ui["next"])}: {E(M.P[nxt]["name"])} →</a></div>')
    out.append('</div></section></main>')
    out.append(footer(ui))
    out.append(SCRIPT)
    return "".join(out)


def overview(M, lang):
    ui, o = M.UI, M.OVERVIEW
    base = "/ja/features/" if lang == "ja" else "/features/"
    alt = ("/features/", "/ja/features/")
    other = alt[0] if lang == "ja" else alt[1]
    out = [head(ui, f'{o["title"]} — ZENOS', o["lead"], base, alt), nav(ui, other), '<main><section class="hero"><div class="wrap">']
    out.append(f'<span class="pill">{E(ui["pill"])}</span><p class="eyebrow" style="margin-top:28px">{E(ui["features"])}</p><h1>{E(o["h1"])}</h1><p class="lead">{E(o["lead"])}</p>')
    out.append('<div class="tags">' + "".join(tag(t, lang) for t in o["legend"]) + '</div>')
    out.append('<div class="grid g3 fgrid">')
    for slug in EN.ORDER:
        d = M.P[slug]
        hl = " hl" if slug == "leak-stop" else ""
        out.append(f'<a class="card fcard{hl}" href="{base}{slug}/">{tag(d["tags"][0], lang)}<h3>{E(d["name"])}</h3><p>{E(d["card"])}</p><span class="more">{E(o["more"])}</span></a>')
    out.append('</div><div class="ctas" style="margin-top:40px">')
    for k, (l, h) in enumerate(ui["cta"]):
        out.append(f'<a class="btn{" p" if k == 0 else ""}" href="{h}">{E(l)}</a>')
    out.append('</div></div></section></main>')
    out.append(footer(ui))
    out.append(SCRIPT)
    return "".join(out)


def write(p, s):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        f.write(s)


def main(site):
    for M, lang, root in ((EN, "en", "features"), (JA, "ja", "ja/features")):
        write(os.path.join(site, root, "index.html"), overview(M, lang))
        for slug in EN.ORDER:
            write(os.path.join(site, root, slug, "index.html"), page(M, slug, lang))
    print("ok", len(EN.ORDER) * 2 + 2, "pages")


if __name__ == "__main__":
    main(sys.argv[1])
