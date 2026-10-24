"""Render docs/architecture.d2 -> docs/images/architecture.png.

Uses the Kroki online renderer for D2, inlines the referenced icon SVGs as
data URIs (an <img>-embedded SVG can't load remote images), then rasterises
with headless Chrome at 2x.

    python3 scripts/render_architecture.py
"""
import base64
import os
import re
import subprocess
import tempfile
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "docs", "architecture.d2")
OUT = os.path.join(ROOT, "docs", "images", "architecture.png")
CHROME = os.environ.get("CHROME", "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")


def fetch(url, data=None):
    req = urllib.request.Request(url, data=data, headers={
        "Content-Type": "text/plain", "User-Agent": "truesignal-docs"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read(), r.headers.get_content_type()


def main():
    svg, _ = fetch("https://kroki.io/d2/svg", open(SRC, "rb").read())
    svg = svg.decode()

    def inline(m):
        body, ctype = fetch(m.group(2).replace("&amp;", "&"))
        if "svg" in ctype or body.lstrip().startswith(b"<"):
            ctype = "image/svg+xml"
        return f'{m.group(1)}="data:{ctype};base64,{base64.b64encode(body).decode()}"'

    svg = re.sub(r'(href|xlink:href)="(https?://[^"]+)"', inline, svg)
    vb = [float(x) for x in re.search(r'viewBox="([^"]+)"', svg).group(1).split()]
    w, h = int(vb[2]), int(vb[3])
    with tempfile.TemporaryDirectory() as tmp:
        page = os.path.join(tmp, "a.html")
        with open(page, "w") as f:
            f.write(f'<html><body style="margin:0;background:#fff">'
                    f'<div style="width:{w}px;height:{h}px">{svg}</div></body></html>')
        subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars",
                        "--force-device-scale-factor=2", f"--window-size={w},{h}",
                        f"--user-data-dir={tmp}/p", f"--screenshot={OUT}", f"file://{page}"],
                       check=True, capture_output=True)
    print(f"wrote {OUT} ({w}x{h} @2x)")


if __name__ == "__main__":
    main()
