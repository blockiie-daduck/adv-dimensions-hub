#!/usr/bin/env python3
"""Generate blank ad templates (PSD, AI, EPS, SVG, PDF, PNG) for every platform/size
in data/platforms.json, plus data/templates-manifest.json and data/hub-data.js.

Pure standard library: no pip install required.
Usage:  python3 scripts/generate_templates.py [--only platform-id ...]
"""
import argparse
import itertools
import json
import re
import shutil
import struct
import sys
import zipfile
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
TPL = ROOT / "templates"

LAYER_ORDER = ["Artwork", "Platform UI", "Safe Zone", "Trim", "Bleed", "Guides"]  # bottom -> top
LOCKED = {"Platform UI", "Safe Zone", "Trim", "Bleed", "Guides"}


def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def fmt_num(n):
    return ("%g" % round(n, 3)).replace(".", "p")


# --------------------------------------------------------------------------- geometry
class Spec:
    """Everything needed to draw one template, in pixels at `dpi`."""

    def __init__(self, platform, size, colors):
        self.platform = platform
        self.section = platform["section"]
        self.colors = colors
        self.label = size["label"]
        if self.section == "digital":
            self.dpi = 72
            self.mode = "RGB"
            self.W, self.H = int(size["w"]), int(size["h"])
            self.bleed = 0
            self.safe = max(4, round(min(self.W, self.H) * 0.05))
            self.thick = max(1, round(max(self.W, self.H) / 900))
            self.title = "%s %dx%d" % (platform["name"], self.W, self.H)
            self.key = "%dx%d" % (self.W, self.H)
            self.trim_w, self.trim_h = self.W, self.H
            self.Wf, self.Hf = float(self.W), float(self.H)
        else:
            self.dpi = int(platform.get("dpi", 300))
            self.mode = "CMYK"
            bleed_in = float(platform.get("bleedIn", 0.125))
            safe_in = float(platform.get("safeIn", 0.25))
            # Very large formats (billboards, posters) are built at a reduced resolution so the
            # template stays openable; 300 dpi at 48 ft would be gigapixels.
            full_w = float(size["wIn"]) + 2 * bleed_in
            full_h = float(size["hIn"]) + 2 * bleed_in
            for cand in (self.dpi, 150, 100, 50, 30, 20, 12):
                if cand <= self.dpi and full_w * cand * full_h * cand <= 25e6:
                    self.dpi = cand
                    break
            else:
                self.dpi = 12
            self.bleed = bleed_in * self.dpi  # exact (may be fractional px, e.g. 37.5)
            self.safe = safe_in * self.dpi
            self.trim_w = float(size["wIn"]) * self.dpi
            self.trim_h = float(size["hIn"]) * self.dpi
            self.Wf = self.trim_w + 2 * self.bleed
            self.Hf = self.trim_h + 2 * self.bleed
            self.W = int(round(self.Wf))
            self.H = int(round(self.Hf))
            self.thick = 3
            self.title = "%s %s (%sx%s in)" % (platform["name"], size["label"], size["wIn"], size["hIn"])
            self.key = "%s-%sx%sin" % (slug(size["label"]), fmt_num(size["wIn"]), fmt_num(size["hIn"]))
        self.ui = size.get("uiSafeZone") or {}
        self.is_spread = "spread" in self.label.lower()
        self.layers = self._build()

    def _build(self):
        W, H, b, s, t = self.Wf, self.Hf, self.bleed, self.safe, self.thick
        L = {n: [] for n in LAYER_ORDER}
        # Bleed: outer edge of canvas (editorial only)
        if b:
            L["Bleed"].append(("outline", 0, 0, W, H, t))
        # Trim: trim line (editorial) or canvas edge (digital)
        L["Trim"].append(("outline", b, b, W - b, H - b, t))
        # Safe zone
        L["Safe Zone"].append(("outline", b + s, b + s, W - b - s, H - b - s, t))
        # Guides: centre crosshair (+ gutter lines for spreads)
        cx, cy = W / 2, H / 2
        L["Guides"].append(("vline", cx, b, H - b, t))
        L["Guides"].append(("hline", cy, b, W - b, t))
        if self.is_spread:
            g = round(0.5 * self.dpi)
            L["Guides"].append(("vline", cx - g, b, H - b, t))
            L["Guides"].append(("vline", cx + g, b, H - b, t))
        # Platform UI overlays (only where the platform documents them)
        u = self.ui
        if u.get("top"):
            L["Platform UI"].append(("fill", 0, 0, W, int(u["top"]), 64))
        if u.get("bottom"):
            L["Platform UI"].append(("fill", 0, H - int(u["bottom"]), W, H, 64))
        if u.get("left"):
            L["Platform UI"].append(("fill", 0, 0, int(u["left"]), H, 64))
        if u.get("right"):
            L["Platform UI"].append(("fill", W - int(u["right"]), 0, W, H, 64))
        # layer name -> (colour key, ops); drop empty layers except Artwork
        out = []
        ckey = {"Platform UI": "ui", "Safe Zone": "safe", "Trim": "trim", "Bleed": "bleed", "Guides": "guides", "Artwork": None}
        for n in LAYER_ORDER:
            if L[n] or n == "Artwork":
                out.append((n, ckey[n], L[n]))
        return out

    def color(self, key, mode=None):
        c = self.colors[key]
        return c["cmyk"] if (mode or self.mode) == "CMYK" else c["rgb"]


def op_rects(op):
    """Decompose an op into plain filled rectangles (x0,y0,x1,y1,alpha)."""
    kind = op[0]
    if kind == "outline":
        _, x0, y0, x1, y1, t = op
        return [(x0, y0, x1, y0 + t, 255), (x0, y1 - t, x1, y1, 255), (x0, y0, x0 + t, y1, 255), (x1 - t, y0, x1, y1, 255)]
    if kind == "vline":
        _, x, y0, y1, t = op
        return [(x - t // 2, y0, x - t // 2 + t, y1, 255)]
    if kind == "hline":
        _, y, x0, x1, t = op
        return [(x0, y - t // 2, x1, y - t // 2 + t, 255)]
    if kind == "fill":
        _, x0, y0, x1, y1, a = op
        return [(x0, y0, x1, y1, a)]
    raise ValueError(kind)


# --------------------------------------------------------------------------- raster helpers
def paint(plane, W, H, rects, value_for_alpha):
    for x0, y0, x1, y1, a in rects:
        x0, x1 = max(0, int(round(x0))), min(W, int(round(x1)))
        y0, y1 = max(0, int(round(y0))), min(H, int(round(y1)))
        if x1 <= x0 or y1 <= y0:
            continue
        row = bytes([value_for_alpha(a)]) * (x1 - x0)
        for y in range(y0, y1):
            plane[y * W + x0:y * W + x1] = row


def packbits(row):
    out = bytearray()
    lit = bytearray()

    def flush():
        while lit:
            chunk = lit[:128]
            del lit[:128]
            out.append(len(chunk) - 1)
            out.extend(chunk)

    for val, grp in itertools.groupby(row):
        n = len(list(grp))
        if n >= 3:
            flush()
            while n > 0:
                m = min(n, 128)
                out.append((257 - m) & 0xFF)
                out.append(val)
                n -= m
        else:
            lit.extend(bytes([val]) * n)
    flush()
    return bytes(out)


def rle_plane(plane, W, H):
    """PackBits-encode a W*H plane. Returns (row byte counts, data). Memoised per distinct row."""
    memo = {}
    counts = []
    chunks = []
    for y in range(H):
        row = bytes(plane[y * W:(y + 1) * W])
        enc = memo.get(row)
        if enc is None:
            enc = packbits(row)
            memo[row] = enc
        counts.append(len(enc))
        chunks.append(enc)
    return counts, b"".join(chunks)


# --------------------------------------------------------------------------- PSD
def psd_channel_data(plane, W, H):
    counts, data = rle_plane(plane, W, H)
    return struct.pack(">H", 1) + struct.pack(">%dH" % H, *counts) + data


def build_psd(spec):
    W, H, mode = spec.W, spec.H, spec.mode
    nch = 3 if mode == "RGB" else 4
    cmyk = mode == "CMYK"
    bg = 255  # stored value for "paper": white RGB / zero ink (inverted CMYK)

    def stored(c, ink):  # CMYK stored inverted; RGB direct
        return (255 - round(ink * 2.55)) if cmyk else ink

    layer_records = bytearray()
    layer_data = bytearray()
    layer_total = 0
    for name, ckey, ops in spec.layers:
        mask = bytearray(W * H)
        rects = [r for op in ops for r in op_rects(op)]
        paint(mask, W, H, rects, lambda a: a)
        chans = []  # (channel id, encoded bytes)
        for ci in range(nch):
            if ckey is None:
                plane = bytearray([bg]) * (W * H) if False else bytearray(W * H)
                if cmyk:
                    plane = bytearray(b"\xff") * (W * H)
            else:
                col = spec.color(ckey)[ci]
                if not cmyk:
                    val = col
                else:
                    val = 255 - round(col * 2.55)
                table = bytes([(255 if cmyk else 0)] + [val] * 255)
                plane = bytearray(mask.translate(table))
            chans.append((ci, psd_channel_data(plane, W, H)))
        chans.append((-1, psd_channel_data(mask, W, H)))
        pname = name.encode("ascii")[:31]
        pascal = bytes([len(pname)]) + pname
        pascal += b"\0" * ((-len(pascal)) % 4)
        extra = b""
        if name in LOCKED:
            extra = b"8BIM" + b"lspf" + struct.pack(">I", 4) + struct.pack(">I", 0x80000000)
        extra_len = 4 + 4 + len(pascal) + len(extra)
        rec = struct.pack(">iiii", 0, 0, H, W)
        rec += struct.pack(">H", len(chans))
        for cid, d in chans:
            rec += struct.pack(">hI", cid, len(d))
        rec += b"8BIM" + b"norm" + bytes([255, 0, 0, 0])
        rec += struct.pack(">I", extra_len)
        rec += struct.pack(">I", 0)  # layer mask data
        rec += struct.pack(">I", 0)  # blending ranges
        rec += pascal + extra
        layer_records += rec
        for _, d in chans:
            layer_data += d
        layer_total += 1
        del mask

    layer_info = struct.pack(">h", layer_total) + bytes(layer_records) + bytes(layer_data)
    if len(layer_info) % 2:
        layer_info += b"\0"
    lm_body = struct.pack(">I", len(layer_info)) + layer_info + struct.pack(">I", 0)
    layer_mask_section = struct.pack(">I", len(lm_body)) + lm_body

    # merged composite (white paper + all guides, flattened)
    planes = [bytearray([bg]) * (W * H) for _ in range(nch)]
    for name, ckey, ops in spec.layers:
        if ckey is None:
            continue
        col = spec.color(ckey)
        for r in (r for op in ops for r in op_rects(op)):
            for ci in range(nch):
                ink = col[ci]
                alpha = r[4] / 255.0
                if cmyk:
                    paper_ink = 0
                    blended = paper_ink + (ink - paper_ink) * alpha
                    v = 255 - round(blended * 2.55)
                else:
                    v = round(255 + (ink - 255) * alpha)
                paint(planes[ci], W, H, [r], lambda a, v=v: v)
    counts_all, data_all = [], []
    for p in planes:
        c, d = rle_plane(p, W, H)
        counts_all += c
        data_all.append(d)
    merged = struct.pack(">H", 1) + struct.pack(">%dH" % (H * nch), *counts_all) + b"".join(data_all)

    dpi_fixed = spec.dpi << 16
    res = struct.pack(">IHHHHH", dpi_fixed, 1, 1, 0, 0, 0)  # placeholder, rebuilt below
    res = struct.pack(">IHHIHH", dpi_fixed, 1, 1, dpi_fixed, 1, 1)
    block = b"8BIM" + struct.pack(">H", 0x03ED) + b"\0\0" + struct.pack(">I", len(res)) + res
    resources = struct.pack(">I", len(block)) + block

    header = b"8BPS" + struct.pack(">H", 1) + b"\0" * 6 + struct.pack(">HIIHH", nch, H, W, 8, 3 if mode == "RGB" else 4)
    return header + struct.pack(">I", 0) + resources + layer_mask_section + merged


# --------------------------------------------------------------------------- vector formats
def rgb01(c):
    return " ".join("%.3f" % (v / 255.0) for v in c)


def cmyk01(c):
    return " ".join("%.3f" % (v / 100.0) for v in c)


def blend_to_white(c, alpha, mode):
    a = alpha / 255.0
    if mode == "CMYK":
        return [v * a for v in c]
    return [255 + (v - 255) * a for v in c]


def pt_scale(spec):
    return 72.0 / spec.dpi


def build_svg(spec):
    W, H = spec.Wf, spec.Hf
    u = "in" if spec.section == "editorial" else "px"
    wd = ("%g" % round(W / spec.dpi, 4)) if u == "in" else ("%g" % W)
    hd = ("%g" % round(H / spec.dpi, 4)) if u == "in" else ("%g" % H)
    out = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<svg xmlns="http://www.w3.org/2000/svg" xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape" '
        'xmlns:sodipodi="http://sodipodi.sourceforge.net/DTD/sodipodi-0.dtd" width="%s%s" height="%s%s" viewBox="0 0 %g %g">' % (wd, u, hd, u, W, H),
        "<title>%s</title>" % spec.title,
        "<desc>%s | %s | %d dpi | guides on locked layers. Delete or hide guide layers before export.</desc>" % (spec.title, spec.mode, spec.dpi),
        '<g id="Background" inkscape:groupmode="layer" inkscape:label="Background"><rect width="%g" height="%g" fill="#ffffff"/></g>' % (W, H),
    ]
    for name, ckey, ops in spec.layers:
        lid = name.replace(" ", "-")
        lock = ' sodipodi:insensitive="true"' if name in LOCKED else ""
        out.append('<g id="%s" inkscape:groupmode="layer" inkscape:label="%s"%s>' % (lid, name, lock))
        if ckey:
            col = "rgb(%d,%d,%d)" % tuple(spec.colors[ckey]["rgb"])
            for op in ops:
                if op[0] == "outline":
                    _, x0, y0, x1, y1, t = op
                    out.append('<rect x="%g" y="%g" width="%g" height="%g" fill="none" stroke="%s" stroke-width="%g"/>' % (x0 + t / 2, y0 + t / 2, x1 - x0 - t, y1 - y0 - t, col, t))
                elif op[0] == "vline":
                    _, x, y0, y1, t = op
                    out.append('<line x1="%g" y1="%g" x2="%g" y2="%g" stroke="%s" stroke-width="%g" stroke-dasharray="%g %g"/>' % (x, y0, x, y1, col, t, t * 6, t * 4))
                elif op[0] == "hline":
                    _, y, x0, x1, t = op
                    out.append('<line x1="%g" y1="%g" x2="%g" y2="%g" stroke="%s" stroke-width="%g" stroke-dasharray="%g %g"/>' % (x0, y, x1, y, col, t, t * 6, t * 4))
                elif op[0] == "fill":
                    _, x0, y0, x1, y1, a = op
                    out.append('<rect x="%g" y="%g" width="%g" height="%g" fill="%s" fill-opacity="%.2f"/>' % (x0, y0, x1 - x0, y1 - y0, col, a / 255.0))
        out.append("</g>")
    out.append("</svg>")
    return "\n".join(out).encode("utf-8")


def build_pdf(spec):
    k = pt_scale(spec)
    Wp, Hp = spec.Wf * k, spec.Hf * k
    cmyk = spec.mode == "CMYK"
    stroke_w = 0.5 if cmyk else max(0.75, spec.thick * k)

    def Y(y):
        return Hp - y * k

    content = []
    ocgs = []
    for name, ckey, ops in spec.layers:
        idx = len(ocgs)
        ocgs.append(name)
        content.append("/OC /oc%d BDC" % idx)
        if ckey:
            c = spec.color(ckey)
            col = cmyk01(c) if cmyk else rgb01(c)
            ks, kf = ("K", "k") if cmyk else ("RG", "rg")
            content.append("q %s %s %g w [%g %g] 0 d" % (col, ks, stroke_w, stroke_w * 6, stroke_w * 4))
            for op in ops:
                if op[0] == "outline":
                    _, x0, y0, x1, y1, t = op
                    content.append("%g %g %g %g re S" % (x0 * k, Y(y1), (x1 - x0) * k, (y1 - y0) * k))
                elif op[0] == "vline":
                    _, x, y0, y1, t = op
                    content.append("%g %g m %g %g l S" % (x * k, Y(y0), x * k, Y(y1)))
                elif op[0] == "hline":
                    _, y, x0, x1, t = op
                    content.append("%g %g m %g %g l S" % (x0 * k, Y(y), x1 * k, Y(y)))
                elif op[0] == "fill":
                    _, x0, y0, x1, y1, a = op
                    content.append("/GS1 gs %s %s %g %g %g %g re f" % (col, kf, x0 * k, Y(y1), (x1 - x0) * k, (y1 - y0) * k))
            content.append("Q")
        content.append("EMC")
    stream = "\n".join(content).encode("ascii")

    objs = []

    def add(b):
        objs.append(b if isinstance(b, bytes) else b.encode("ascii"))
        return len(objs)

    n_oc = len(ocgs)
    first_ocg = 5
    ocg_refs = " ".join("%d 0 R" % (first_ocg + i) for i in range(n_oc))
    add("<< /Type /Catalog /Pages 2 0 R /OCProperties << /OCGs [%s] /D << /Order [%s] /ON [%s] >> >> >>" % (ocg_refs, ocg_refs, ocg_refs))
    add("<< /Type /Pages /Kids [3 0 R] /Count 1 >>")
    props = " ".join("/oc%d %d 0 R" % (i, first_ocg + i) for i in range(n_oc))
    boxes = ""
    if spec.bleed:
        b = spec.bleed * k
        boxes = " /TrimBox [%g %g %g %g] /BleedBox [0 0 %g %g]" % (b, b, Wp - b, Hp - b, Wp, Hp)
    add("<< /Type /Page /Parent 2 0 R /MediaBox [0 0 %g %g]%s /Contents 4 0 R /Resources << /Properties << %s >> /ExtGState << /GS1 << /ca 0.25 /CA 0.25 >> >> >> >>" % (Wp, Hp, boxes, props))
    add(b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream")
    for name in ocgs:
        add("<< /Type /OCG /Name (%s) >>" % name)
    add("<< /Title (%s) /Creator (Ad Dimensions Toolkit) >>" % spec.title.replace("(", "").replace(")", ""))

    out = bytearray(b"%PDF-1.5\n%\xe2\xe3\xcf\xd3\n")
    offs = []
    for i, o in enumerate(objs, 1):
        offs.append(len(out))
        out += b"%d 0 obj\n" % i + o + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1)
    for o in offs:
        out += b"%010d 00000 n \n" % o
    out += b"trailer\n<< /Size %d /Root 1 0 R /Info %d 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, len(objs), xref)
    return bytes(out)


def build_eps(spec):
    k = pt_scale(spec)
    Wp, Hp = spec.Wf * k, spec.Hf * k
    cmyk = spec.mode == "CMYK"
    sw = 0.5 if cmyk else max(0.75, spec.thick * k)

    def Y(y):
        return Hp - y * k

    L = [
        "%!PS-Adobe-3.0 EPSF-3.0",
        "%%%%BoundingBox: 0 0 %d %d" % (int(Wp + 0.999), int(Hp + 0.999)),
        "%%%%HiResBoundingBox: 0 0 %g %g" % (Wp, Hp),
        "%%%%Title: %s" % spec.title,
        "%%Creator: Ad Dimensions Toolkit",
        "%%%%DocumentProcessColors: %s" % ("Cyan Magenta Yellow Black" if cmyk else "Red Green Blue"),
        "%%EndComments",
        "%% Guides only. EPS has no layers: delete the guide strokes or place your artwork beneath them.",
        "gsave",
        "%g setlinewidth" % sw,
    ]
    for name, ckey, ops in spec.layers:
        if not ckey:
            continue
        L.append("%% layer: %s" % name)
        c = spec.color(ckey)
        for op in ops:
            if op[0] == "fill":
                cc = blend_to_white(c, op[5], spec.mode)
                L.append("%s %s" % (cmyk01(cc) if cmyk else rgb01(cc), "setcmykcolor" if cmyk else "setrgbcolor"))
                _, x0, y0, x1, y1, a = op
                L.append("%g %g %g %g rectfill" % (x0 * k, Y(y1), (x1 - x0) * k, (y1 - y0) * k))
                continue
            L.append("%s %s" % (cmyk01(c) if cmyk else rgb01(c), "setcmykcolor" if cmyk else "setrgbcolor"))
            if op[0] == "outline":
                _, x0, y0, x1, y1, t = op
                L.append("[] 0 setdash %g %g %g %g rectstroke" % (x0 * k, Y(y1), (x1 - x0) * k, (y1 - y0) * k))
            elif op[0] == "vline":
                _, x, y0, y1, t = op
                L.append("[%g %g] 0 setdash newpath %g %g moveto %g %g lineto stroke" % (sw * 6, sw * 4, x * k, Y(y0), x * k, Y(y1)))
            elif op[0] == "hline":
                _, y, x0, x1, t = op
                L.append("[%g %g] 0 setdash newpath %g %g moveto %g %g lineto stroke" % (sw * 6, sw * 4, x0 * k, Y(y), x1 * k, Y(y)))
    L += ["grestore", "showpage", "%%EOF", ""]
    return "\n".join(L).encode("ascii")


def build_png(spec):
    """Indexed transparent guide overlay (palette PNG keeps big print sizes tiny)."""
    W, H = spec.W, spec.H
    pal = [(0, 0, 0)]
    trns = [0]
    plane = bytearray(W * H)
    for name, ckey, ops in spec.layers:
        if not ckey:
            continue
        rgb = tuple(spec.colors[ckey]["rgb"])
        has_fill = any(op[0] == "fill" for op in ops)
        idx_line = len(pal)
        pal.append(rgb)
        trns.append(255)
        idx_fill = idx_line
        if has_fill:
            idx_fill = len(pal)
            pal.append(rgb)
            trns.append(64)
        rects = [r for op in ops for r in op_rects(op)]
        paint(plane, W, H, rects, lambda a, il=idx_line, jf=idx_fill: il if a == 255 else jf)
    counts_memo = {}
    rows = []
    for y in range(H):
        row = bytes(plane[y * W:(y + 1) * W])
        rows.append(b"\x00" + row)
    raw = b"".join(rows)

    def chunk(t, d):
        c = struct.pack(">I", len(d)) + t + d
        return c + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)

    ppm = round(spec.dpi / 0.0254)
    png = b"\x89PNG\r\n\x1a\n"
    png += chunk(b"IHDR", struct.pack(">IIBBBBB", W, H, 8, 3, 0, 0, 0))
    png += chunk(b"PLTE", b"".join(bytes(p) for p in pal))
    png += chunk(b"tRNS", bytes(trns))
    png += chunk(b"pHYs", struct.pack(">IIB", ppm, ppm, 1))
    png += chunk(b"IDAT", zlib.compress(raw, 9))
    png += chunk(b"IEND", b"")
    return png


BUILDERS = {"svg": build_svg, "pdf": build_pdf, "eps": build_eps, "png": build_png, "psd": build_psd}


# --------------------------------------------------------------------------- driver
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="*", help="platform ids to (re)generate")
    ap.add_argument("--formats", nargs="*", default=["psd", "ai", "eps", "svg", "pdf", "png"])
    args = ap.parse_args()

    platforms = json.loads((DATA / "platforms.json").read_text())
    formats = json.loads((DATA / "formats.json").read_text())
    colors = formats["guideColors"]
    manifest = {}
    TPL.mkdir(exist_ok=True)
    for p in platforms:
        if args.only and p["id"] not in args.only:
            continue
        pdir = TPL / p["id"]
        if pdir.exists():
            shutil.rmtree(pdir)
        pdir.mkdir(parents=True)
        entries = []
        seen = {}
        for size in p["sizes"]:
            spec = Spec(p, size, colors)
            if spec.key in seen:
                seen[spec.key] += 1
                spec.key += "-%d" % seen[spec.key]
            else:
                seen[spec.key] = 1
            files = []
            pdf_bytes = None
            for ext in args.formats:
                fname = "%s-%s.%s" % (p["id"], spec.key, ext)
                target = pdir / fname
                if ext == "ai":
                    pdf_bytes = pdf_bytes or build_pdf(spec)
                    target.write_bytes(pdf_bytes)
                else:
                    data = BUILDERS[ext](spec)
                    if ext == "pdf":
                        pdf_bytes = data
                    target.write_bytes(data)
                files.append({"ext": ext, "path": "templates/%s/%s" % (p["id"], fname)})
            # manually supplied masters (e.g. Affinity .af, Figma .fig, PDF/X)
            for man in (ROOT / "templates" / "_manual" / p["id"], ROOT / "templates" / "_manual" / "_all"):
                if man.exists():
                    for f in sorted(man.glob(spec.key + ".*")):
                        files.append({"ext": f.suffix.lstrip("."), "path": str(f.relative_to(ROOT))})
            entries.append({"key": spec.key, "w": spec.W, "h": spec.H, "dpi": spec.dpi, "files": files})
            print("  %-16s %-34s %dx%d px" % (p["id"], spec.key, spec.W, spec.H))
        zpath = pdir / ("%s-all-templates.zip" % p["id"])
        with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
            for f in sorted(pdir.iterdir()):
                if f != zpath:
                    z.write(f, f.name)
        manifest[p["id"]] = {"sizes": entries, "zip": "templates/%s/%s" % (p["id"], zpath.name)}

    mpath = DATA / "templates-manifest.json"
    if args.only and mpath.exists():
        old = json.loads(mpath.read_text())
        old.update(manifest)
        manifest = old
    mpath.write_text(json.dumps(manifest, indent=1))
    # file:// friendly bundle so index.html also works when double-clicked
    bundle = {"platforms": platforms, "formats": formats, "manifest": manifest}
    (DATA / "hub-data.js").write_text("window.HUB_DATA = " + json.dumps(bundle) + ";\n")
    print("done: %d platforms" % len(manifest))


if __name__ == "__main__":
    sys.exit(main())
