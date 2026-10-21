#!/usr/bin/env python3
"""GLB/OBJ modelinden hızlı 2B görünüş (PNG) üretir — headless'ta çalışır.

trimesh'in etkileşimli penceresi ekran ister; bu script saf matplotlib ile
(painter's algorithm + basit lambert gölgelendirme) görünüş çizer.

Kullanim:
    python scripts/elevation.py out/bina.glb -o out/gorunus.png
    python scripts/elevation.py out/bina.glb --view top
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import trimesh  # noqa: E402
from matplotlib.collections import PolyCollection  # noqa: E402

VIEWS = {
    "front": (0, 1),    # X-Yatay, Z-Dikey
    "side":  (1, 2),
    "top":   (0, 1),
    "iso":   None,
}


def iso_project(v, az=35.0, el=25.0):
    az, el = np.radians(az), np.radians(el)
    Rz = np.array([[np.cos(az), -np.sin(az), 0],
                   [np.sin(az),  np.cos(az), 0], [0, 0, 1]])
    Ry = np.array([[np.cos(el), 0, np.sin(el)], [0, 1, 0],
                   [-np.sin(el), 0, np.cos(el)]])
    p = v @ Rz.T @ Ry.T
    return p[:, 0], p[:, 2], p[:, 1]     # (yatay, dikey, derinlik)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("model")
    ap.add_argument("-o", "--out", default=None)
    ap.add_argument("--view", default="iso", choices=list(VIEWS))
    ap.add_argument("--dpi", type=int, default=150)
    ap.add_argument("--alpha", type=float, default=1.0)
    a = ap.parse_args()

    src = Path(a.model)
    sc = trimesh.load(src, force="scene")
    out = Path(a.out) if a.out else src.with_name(
        f"{src.stem}_{a.view}.png")

    fig, ax = plt.subplots(figsize=(11, 13) if a.view != "top" else (11, 11))

    all_pts = []
    for name, g in sorted(sc.geometry.items()):
        v = np.asarray(g.vertices, dtype=float)
        f = np.asarray(g.faces, dtype=np.int64)
        if len(f) == 0:
            continue
        all_pts.append(v)
        # yüzey renkleri
        try:
            vc = np.asarray(g.visual.vertex_colors)[:, :3] / 255.0
        except Exception:  # noqa: BLE001
            vc = np.full((len(v), 3), 0.7)
        fc = vc[f].mean(axis=1)
        # yüzey normalleri -> gölgelendirme
        n = g.face_normals
        light = np.array([0.45, 0.75, 0.5])
        light /= np.linalg.norm(light)
        shade = 0.45 + 0.55 * np.abs(n @ light)

        if a.view == "iso":
            h, d, dep = iso_project(v)
            verts2 = np.stack([h, d], axis=1)
        else:
            i, j = VIEWS[a.view]
            verts2 = v[:, [i, j]]
            dep = v[:, 2] if a.view != "top" else v[:, 2]
        tri = verts2[f]
        depth = dep[f].mean(axis=1)
        order = np.argsort(depth)
        cols = np.clip(fc * shade[:, None], 0, 1)
        ax.add_collection(PolyCollection(
            tri[order], facecolors=cols[order], edgecolors="none",
            alpha=a.alpha, closed=True))

    pts = np.vstack(all_pts)
    if a.view == "iso":
        h, d, _ = iso_project(pts)
        xs, ys = h, d
        ax.set_xlabel("≈ X+Y"), ax.set_ylabel("Z (m)")
    else:
        i, j = VIEWS[a.view]
        xs, ys = pts[:, i], pts[:, j]
        ax.set_xlabel("XYZ"[i] + " (m)"), ax.set_ylabel("XYZ"[j] + " (m)")
    ax.set_xlim(xs.min(), xs.max())
    ax.set_ylim(ys.min(), ys.max())
    ax.set_aspect("equal", adjustable="box")
    ax.set_title(f"{src.name} — {a.view} görünüşü", fontsize=12)
    ax.grid(False)
    ax.set_facecolor("#15181d")
    fig.patch.set_facecolor("#15181d")
    ax.tick_params(colors="#9fb4c7")
    for s in (*ax.spines.values(),):
        s.set_color("#2b323b")
    ax.xaxis.label.set_color("#9fb4c7")
    ax.yaxis.label.set_color("#9fb4c7")
    ax.title.set_color("#e6e6e6")

    out.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(out, dpi=a.dpi)
    print(f"yazildi: {out}  ({out.stat().st_size / 1024:.0f} KB)")
    print(f"  model boyutu (m): {np.round(sc.extents, 2)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
