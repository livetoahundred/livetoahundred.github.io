"""Import the Claude Design landing page as static HTML.

The design lives in the l2a repo at design/landing-page/ (a copy of the Claude
canvas). It renders with a React runtime; this script opens it in headless
Chrome, takes the rendered page for each language and keeps only the HTML and
CSS, so the published site loads no scripts.

    python3 tools/import_landing.py [/path/to/design/landing-page]
    python3 build.py

It writes src/landing/tr.html and src/landing/en.html and copies the CSS,
fonts and images under assets/lp/. build.py fills in the placeholders:
{{UP}} (the relative path to the site root), {{SIGNUP_ACTION}} and
{{SIGNUP_HIDDEN}} (the newsletter form).
"""
import functools
import http.server
import os
import re
import shutil
import subprocess
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DESIGN = Path(sys.argv[1] if len(sys.argv) > 1 else "/home/cem/livetoa100/design/landing-page").resolve()
REPO = DESIGN.parent.parent
CHROME = Path.home() / "chrome-for-testing/chrome-linux64/chrome"
CHROME_LIBS = f"{Path.home()}/chrome-libs:{Path.home()}/chrome-libs/usr/lib/x86_64-linux-gnu"

PAGES = {"tr": "Main.dc.html", "en": "Desktop-EN.dc.html"}
TITLES = {
    "tr": ("livetoahundred · Ne işe yarar, ne yaramaz? Kanıt söylesin.",
           "Her hafta yeni araştırmaları okuyor, her birini tek soruya ve cevabına indiriyoruz. Kaynağıyla birlikte e-postana."),
    "en": ("livetoahundred · What works, what doesn't? Let the evidence say.",
           "Each week we read the new research and boil every study down to one question and its answer, with the source."),
}


def serve() -> int:
    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *args):
            pass
    handler = functools.partial(Quiet, directory=str(REPO))
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd.server_address[1]


def render(port: int, page: str) -> str:
    url = f"http://127.0.0.1:{port}/{DESIGN.relative_to(REPO)}/{page}"
    env = dict(os.environ, LD_LIBRARY_PATH=CHROME_LIBS)
    out = subprocess.run(
        [str(CHROME), "--headless=new", "--no-sandbox", "--disable-gpu", "--virtual-time-budget=15000",
         "--window-size=1440,5600", "--dump-dom", url],
        capture_output=True, text=True, env=env, timeout=120, check=True).stdout
    if "data-dc-tpl" not in out:
        raise SystemExit(f"{page}: the page did not render")
    return out


def clean(dom: str, lang: str) -> str:
    head, _, rest = dom.partition("</head>")
    body = rest.split("<body>", 1)[1].rsplit("</body>", 1)[0]
    styles = "\n".join(re.findall(r"<style\b.*?</style>", head, re.S))
    body = re.sub(r"<script\b.*?</script>", "", body, flags=re.S)
    body = re.sub(r' data-dc-tpl="[^"]*"', "", body)

    # Language switch: the buttons become links between the two pages.
    def lang_link(m: re.Match) -> str:
        code, style = m.group(2), m.group(1)
        href = "{{UP}}" if code == "TR" else "{{UP}}en/"
        current = ' aria-current="page"' if code.lower() == lang else ""
        style = style.replace("cursor: pointer;", "").replace("cursor: default;", "")
        return (f'<a href="{href}" hreflang="{code.lower()}"{current} style="{style} display: inline-flex; '
                f'align-items: center; justify-content: center; box-sizing: border-box; text-decoration: none;">{code}</a>')
    body, n = re.subn(r'<button type="button" aria-pressed="(?:true|false)" style="([^"]*)">(TR|EN)</button>', lang_link, body)
    if n != 2:
        raise SystemExit(f"{lang}: expected 2 language buttons, found {n}")

    # Newsletter forms post to the provider; build.py fills the placeholders.
    body, n = re.subn(r"<form\b", '<form method="post" action="{{SIGNUP_ACTION}}"', body)
    body = body.replace("</form>", "{{SIGNUP_HIDDEN}}</form>")
    body = body.replace('name="email"', 'name="EMAIL"')
    body = re.sub(r'href="#"(?=[^>]*>(?:KVKK|Privacy|privacy))', 'href="{{UP}}privacy/#' + lang + '"', body)
    if 'href="#"' in body:
        raise SystemExit(f"{lang}: a link still points to #")

    legal = {
        "tr": [("newsletter/", "Bülten"), ("privacy/#tr", "Gizlilik"), ("terms/#tr", "Kullanım koşulları"),
               ("data-deletion/#tr", "Veri silme"), ("mailto:info.live2a100@gmail.com", "info.live2a100@gmail.com")],
        "en": [("newsletter/", "Newsletter (Turkish)"), ("privacy/", "Privacy"), ("terms/", "Terms"),
               ("data-deletion/", "Data deletion"), ("mailto:info.live2a100@gmail.com", "info.live2a100@gmail.com")],
    }[lang]
    links = " ".join(
        f'<a href="{h if h.startswith("mailto:") else "{{UP}}" + h}" style="color: #c9ced6;">{t}</a>' for h, t in legal)
    nav = (f'<nav class="lp-legal" aria-label="{"Yasal" if lang == "tr" else "Legal"}" style="background: #15171e; '
           f'border-top: 1px solid rgba(255,255,255,0.12); padding: 18px 20px 28px; display: flex; flex-wrap: wrap; '
           f'gap: 8px 22px; justify-content: center; font-family: \'Archivo\', sans-serif; font-size: 14px;">{links}</nav>')

    title, description = TITLES[lang]
    other = "en" if lang == "tr" else "tr"
    return f"""<!doctype html>
<html lang="{lang}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<meta name="description" content="{description}">
<link rel="alternate" hreflang="{other}" href="{{{{UP}}}}{'en/' if other == 'en' else ''}">
<link rel="icon" type="image/png" sizes="32x32" href="{{{{UP}}}}assets/favicon-32.png">
<link rel="apple-touch-icon" href="{{{{UP}}}}assets/apple-touch-icon.png">
<link rel="stylesheet" href="{{{{UP}}}}assets/lp/l2a-tokens.css">
<link rel="stylesheet" href="{{{{UP}}}}assets/lp/bundle.css">
<link rel="stylesheet" href="{{{{UP}}}}assets/lp/landing.css">
{styles}
</head>
<body style="margin:0; background:#15171e">
{body.strip()}
{nav}
</body>
</html>
"""


def copy_assets() -> None:
    lp = ROOT / "assets" / "lp"
    lp.mkdir(parents=True, exist_ok=True)
    tokens = (DESIGN / "l2a-tokens.css").read_text(encoding="utf-8")
    tokens = tokens.replace("../../templates/assets/fonts/", "../fonts/")
    (lp / "l2a-tokens.css").write_text(tokens, encoding="utf-8")
    shutil.copy(DESIGN / "landing.css", lp / "landing.css")
    shutil.copy(DESIGN.parent / "claude-design/live-to-a-hundred/components/bundle.css", lp / "bundle.css")
    for img in (DESIGN / "uploads").iterdir():
        shutil.copy(img, lp / img.name)
    fonts = REPO / "templates/assets/fonts"
    for name in ("Oswald.woff2", "Archivo.woff2", "JetBrainsMono.woff2", "OFL-JetBrainsMono.txt"):
        shutil.copy(fonts / name, ROOT / "assets/fonts" / name)


def main() -> None:
    port = serve()
    out = ROOT / "src" / "landing"
    out.mkdir(parents=True, exist_ok=True)
    for lang, page in PAGES.items():
        html = clean(render(port, page), lang)
        html = html.replace('src="uploads/', 'src="{{UP}}assets/lp/')
        if "uploads/" in html:
            raise SystemExit(f"{lang}: an image path still points to uploads/")
        (out / f"{lang}.html").write_text(html, encoding="utf-8")
        print("wrote", (out / f"{lang}.html").relative_to(ROOT), f"({len(html) // 1024} KB)")
    copy_assets()
    print("copied assets/lp/ and fonts")


if __name__ == "__main__":
    main()
