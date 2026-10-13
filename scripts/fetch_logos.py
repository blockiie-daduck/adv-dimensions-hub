#!/usr/bin/env python3
"""Fetch brand marks from Simple Icons (CC0, pinned version) and build neutral monogram/icon
fallbacks for brands Simple Icons does not carry. Output: assets/logos/<id>.svg"""
import re
import urllib.request
from pathlib import Path

VERSION = "13.21.0"
OUT = Path(__file__).resolve().parent.parent / "assets" / "logos"
OUT.mkdir(parents=True, exist_ok=True)

# platform id -> (simple-icons slug, brand colour)
SIMPLE = {
    "google-ads": ("googleads", "4285F4"),
    "meta-facebook": ("facebook", "0866FF"),
    "meta-instagram": ("instagram", "E4405F"),
    "linkedin": ("linkedin", "0A66C2"),
    "youtube": ("youtube", "FF0000"),
    "amazon-ads": ("amazon", "FF9900"),
    "tiktok-ads": ("tiktok", "111111"),
    "x-ads": ("x", "111111"),
    "pinterest-ads": ("pinterest", "BD081C"),
}
# platform id -> (monogram text, colour). ZoomInfo and Microsoft use user-supplied PNGs checked in directly.
MONO = {
    "iab-standard": ("IAB", "334155"),
}
# generic print icons: id -> inner svg (24x24 viewBox, stroke icons)
ICON = {
    "magazine": '<path d="M5 4h11a3 3 0 0 1 3 3v13H8a3 3 0 0 1-3-3z"/><path d="M8 8h7M8 12h7M8 16h4"/>',
    "newspaper": '<path d="M4 5h13v14H6a2 2 0 0 1-2-2z"/><path d="M17 9h3v8a2 2 0 0 1-2 2"/><path d="M7 9h7M7 13h7M7 16h4"/>',
    "trade-publication": '<rect x="5" y="4" width="14" height="16" rx="2"/><path d="M8 8h8"/><rect x="8" y="11" width="8" height="5" rx="1"/>',
    "ooh-print": '<rect x="3" y="5" width="18" height="10" rx="1.5"/><path d="M8 15v5M16 15v5"/>',
}

for pid, (slug, color) in SIMPLE.items():
    url = "https://cdn.jsdelivr.net/npm/simple-icons@%s/icons/%s.svg" % (VERSION, slug)
    svg = urllib.request.urlopen(url, timeout=30).read().decode()
    svg = re.sub(r"<title>.*?</title>", "", svg)
    svg = svg.replace("<svg ", '<svg fill="#%s" ' % color, 1)
    (OUT / (pid + ".svg")).write_text(svg)
    print("fetched", pid)

for pid, (txt, color) in MONO.items():
    size = 11 if len(txt) == 1 else 7.5
    (OUT / (pid + ".svg")).write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><rect width="24" height="24" rx="6" fill="#%s"/>'
        '<text x="12" y="16.5" text-anchor="middle" font-family="Helvetica,Arial,sans-serif" font-weight="700" font-size="%s" fill="#fff">%s</text></svg>' % (color, size * 1.5 if len(txt) == 1 else size, txt))
    print("monogram", pid)

for pid, inner in ICON.items():
    (OUT / (pid + ".svg")).write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="#475569" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">%s</svg>' % inner)
    print("icon", pid)
