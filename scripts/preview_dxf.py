#!/usr/bin/env python3
"""DXF planini matplotlib ile hizli 2D onizleme olarak cizer (PNG).

Gorsellestirme hatti: ezdxf -> shapely/trimesh (3B). Bu script sadece
hizli bir "goz atma" aracidir; etkilesimli 3B icin scripts/extrude_demo.py.

Kullanim:
    python scripts/preview_dxf.py data/kavaklik_01.dxf -o out/preview.png
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from pathlib import Path

import ezdxf
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from matplotlib.patches import Polygon as MplPoly  # noqa: E402

# katman -> (renk, kalinlik, dolgu)
STYLE = {
    "Bina_kontur": ("#111111", 1.4, None),
    "C_kolon":     ("#c0392b", 1.0, "#e74c3c"),
    "C_oda":       ("#2c3e50", 0.7, None),
    "C_pencere":   ("#2980b9", 1.0, "#5dade2"),
    "C_merdiven":  ("#7f8c8d", 0.6, "#bdc3c7"),
    "C_kapi":      ("#d35400", 0.8, None),
    "B_balkon":    ("#16a085", 0.9, None),
    "C_baca":      ("#8e44ad", 0.9, None),
    "HavaBaca":    ("#8e44ad", 0.9, None),
    "Merdiven":    ("#7f8c8d", 0.8, None),
    "Merd+Koridor": ("#95a5a6", 0.8, None),
    "Asansör":     ("#27ae60", 1.0, None),
    "C_pafta":     ("#bdc3c7", 0.5, None),
    "dvr_kaba":    ("#f39c12", 0.5, None),
    "dvr_siva":    ("#f1c40f", 0.5, None),
    "0":           ("#34495e", 0.4, None),
}
DEFAULT_STYLE = ("#95a5a6", 0.4, None)
SKIP = {"ic_olcu", "mekanadi"}


def flatten(msp, max_depth=8):
    """INSERT'lari acarak WCS'ye tasinmis (tip, katman, noktalar) listesi."""
    out = []
    stack = [(e, None, 0) for e in msp]
    while stack:
        e, m, depth = stack.pop()
        t = e.dxftype()
        if t == "INSERT" and depth < max_depth:
            try:
                blk = e.block()
            except Exception:  # noqa: BLE001
                blk = None
            if blk is None:
                continue
            try:
                m2 = e.matrix44()
                m = m2 if m is None else m @ m2
            except Exception:  # noqa: BLE001
                pass
            for se in blk:
                stack.append((se, m, depth + 1))
            continue
        if t == "LWPOLYLINE":
            pts = [(p[0], p[1]) for p in e.get_points("xy")]
        elif t == "POLYLINE":
            pts = [(v.dxf.location.x, v.dxf.location.y) for v in e.vertices()]
        elif t == "CIRCLE":
            c, r = e.dxf.center, e.dxf.radius
            n = 24
            import math
            pts = [(c.x + r * math.cos(2 * math.pi * i / n),
                    c.y + r * math.sin(2 * math.pi * i / n)) for i in range(n)]
            pts.append(pts[0])
        else:
            continue
        if m is not None:
            pts = [(m.transform((x, y, 0))[0], m.transform((x, y, 0))[1]) for x, y in pts]
        out.append((t, e.dxf.layer, pts))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("dxf", nargs="?", default="data/kavaklik_01.dxf")
    ap.add_argument("-o", "--out", default="out/preview.png")
    ap.add_argument("--dpi", type=int, default=170)
    ap.add_argument("--layers", default="",
                    help="virgulle ayrilmis katman filtresi (bos = hepsi)")
    ap.add_argument("--bbox", default="",
                    help="xmin,ymin,xmax,ymax -> sadece bu bolgeyi ciz")
    a = ap.parse_args()

    doc = ezdxf.readfile(a.dxf)
    flat = flatten(doc.modelspace())
    keep = set(a.layers.split(",")) if a.layers else None

    by_layer = defaultdict(list)
    for _t, layer, pts in flat:
        if layer in SKIP:
            continue
        if keep and layer not in keep:
            continue
        if len(pts) >= 2:
            by_layer[layer].append(pts)

    fig, ax = plt.subplots(figsize=(16, 12))
    for layer, polys in by_layer.items():
        col, lw, fc = STYLE.get(layer, DEFAULT_STYLE)
        for pts in polys:
            if len(pts) >= 3:
                ax.add_patch(MplPoly(pts, closed=True, fill=fc is not None,
                                     edgecolor=col, facecolor=fc, lw=lw, zorder=2))
            else:
                ax.add_line(Line2D([p[0] for p in pts], [p[1] for p in pts],
                                   color=col, lw=lw, zorder=2))

    ax.set_aspect("equal", adjustable="box")
    if a.bbox:
        x0, y0, x1, y1 = (float(v) for v in a.bbox.split(","))
        ax.set_xlim(x0, x1)
        ax.set_ylim(y0, y1)
    else:
        ax.autoscale_view()
    ax.set_xlabel("X [cm]")
    ax.set_ylabel("Y [cm]")
    ax.set_title(f"{Path(a.dxf).name}  -  katman bazli plan onizleme\n"
                 "(1 birim = 1 cm; $INSUNITS=6 yanlis)", fontsize=11)
    ax.grid(True, lw=0.2, color="#cccccc", zorder=0)
    handles = [Line2D([], [], color=STYLE.get(l, DEFAULT_STYLE)[0],
                      lw=2, label=f"{l} ({len(p)})")
               for l, p in sorted(by_layer.items(), key=lambda kv: -len(kv[1]))]
    ax.legend(handles=handles, fontsize=7, loc="upper left",
              bbox_to_anchor=(1.01, 1.0))
    fig.tight_layout()

    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=a.dpi, bbox_inches="tight")
    print(f"yazildi: {out}  ({out.stat().st_size/1024:.0f} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
