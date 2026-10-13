# Ad Dimensions Toolkit

One place for display and editorial ad specs: dimensions, file types, size limits, rules, best
practices, and downloadable blank templates with bleed/safe-zone guides.

- **Digital display** (still image + GIF): RGB, 72 dpi, pixels.
- **Editorial** (magazine, newspaper, trade, OOH print): CMYK, 300 dpi, inches, 0.125 in bleed where applicable.
- Video specs and brand-guide-driven templates are planned for later versions.

## Run it

No build step. Serve the folder and open it:

```bash
python3 -m http.server 8765
```

then visit http://localhost:8765 (opening `index.html` directly also works). Deploy anywhere static, e.g. GitHub Pages.

## How it's built

| Path | Purpose |
| --- | --- |
| `data/parts/*.json` | Source specs (one file per group, with sources + confidence per platform) |
| `scripts/merge_data.py` | Merges parts into `data/platforms.json` and validates |
| `scripts/generate_templates.py` | Builds every template + `templates-manifest.json` + `hub-data.js` (pure Python, no dependencies) |
| `scripts/fetch_logos.py` | Pulls brand marks from Simple Icons (CC0) and builds fallbacks |
| `data/formats.json` | Color/dpi/bleed presets, guide colors, template formats |
| `templates/` | Generated output (committed so the hosted site works) |
| `templates/_manual/<platform-id>/<size-key>.af` | Drop hand-made masters (Affinity `.af`, Figma `.fig`, PDF/X) here; the generator links them |

After editing specs:

```bash
python3 scripts/merge_data.py && python3 scripts/generate_templates.py
```

Use `--only <platform-id>` to rebuild one platform. Template files use layer/group names
`Artwork`, `Platform UI`, `Safe Zone`, `Trim`, `Bleed`, `Guides`; guide layers are locked where the format allows.

## Template notes

- PSD, AI (PDF-compatible), EPS, SVG, PDF and a transparent PNG guide overlay are generated. `.af`, `.fig` and PDF/X are "coming soon" until a master file is supplied.
- EPS has no layers. PSD files are written by a small custom writer and verified with `psd-tools`; open one in your tool of choice before relying on it for production, and report problems.
- No ICC profile is embedded; set the working profile (sRGB for digital, SWOP/GRACoL or the publication's profile for print) in your app.
- Very large formats (billboards, posters) are built at a reduced resolution so files stay openable; the card shows the actual dpi.

## Accuracy

Specs are informational and change often. Each platform shows a "last verified" date, a confidence level, and its
sources. Several platforms (ZoomInfo DSP, X, TikTok, OOH) have no easily-fetched official spec sheet; those are flagged
low/medium confidence. Editorial sizes are common defaults, so confirm with the publication's rate card.
Found something stale? Use the "Report an issue" link on the card.

## Credits and legal

Platform names and logos are trademarks of their owners and are used only to identify each platform; this project is not
affiliated with or endorsed by them. Brand marks come from [Simple Icons](https://simpleicons.org) (CC0, pinned to v13.21.0).
Code is MIT licensed (see `LICENSE`).
