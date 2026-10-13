#!/usr/bin/env python3
"""Merge data/parts/*.json into data/platforms.json and sanity-check the result."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
parts = sorted((ROOT / "data" / "parts").glob("*.json"))
platforms = []
for f in parts:
    platforms += json.loads(f.read_text())

ORDER = ["zoominfo-dsp", "google-ads", "meta-facebook", "meta-instagram", "youtube", "linkedin", "amazon-ads",
         "microsoft-ads", "tiktok-ads", "x-ads", "pinterest-ads", "iab-standard",
         "magazine", "newspaper", "trade-publication", "ooh-print"]
rank = lambda p: (0 if p["section"] == "digital" else 1, ORDER.index(p["id"]) if p["id"] in ORDER else 99, p["name"])
platforms.sort(key=rank)

for p in platforms:
    logos = sorted((ROOT / "assets" / "logos").glob(p["id"] + ".*"))
    p["logo"] = logos[0].name if logos else "missing.svg"

errors = []
ids = set()
for p in platforms:
    if p["id"] in ids:
        errors.append("duplicate id " + p["id"])
    ids.add(p["id"])
    for k in ("id", "section", "name", "summary", "fileTypes", "rules", "bestPractices", "sizes", "verified"):
        if k not in p:
            errors.append("%s missing %s" % (p["id"], k))
    for s in p.get("sizes", []):
        if p["section"] == "digital" and not (s.get("w") and s.get("h")):
            errors.append("%s bad size %s" % (p["id"], s))
        if p["section"] == "editorial" and not (s.get("wIn") and s.get("hIn")):
            errors.append("%s bad size %s" % (p["id"], s))
if errors:
    print("\n".join(errors))
    sys.exit(1)
(ROOT / "data" / "platforms.json").write_text(json.dumps(platforms, indent=1, ensure_ascii=False))
print("merged %d platforms, %d sizes" % (len(platforms), sum(len(p["sizes"]) for p in platforms)))
