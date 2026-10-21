#!/usr/bin/env python3
"""Tüm binayı kat kat yığarak 3B model üretir.

    bodrum + zemin + 8 normal kat  (10 kat)
    duvarlar: kaba beton + HER İKİ YÜZDE 2 cm sıva kabuğu
    kapı ve pencereler: açıklıklara oturan katı gövdeler

Kullanim:
    python scripts/building.py                       # varsayilan 10 kat
    python scripts/building.py --normal-floors 8 --heights bodrum=300,zemin=320,normal=300
    python scripts/building.py --no-joinery          # sadece duvar/döseme
    python scripts/building.py --list                # pafta + yükseklik özeti
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import numpy as np  # noqa: E402
import trimesh  # noqa: E402

import cad2d.building as cb  # noqa: E402
import cad2d.dxfio as dx  # noqa: E402
import cad2d.solid as so  # noqa: E402
import cad2d.view as vw  # noqa: E402

# parça adı -> renk
COLORS = {
    "döseme":        (0.62, 0.62, 0.66),
    "duvar_kaba":    (0.80, 0.78, 0.73),
    "sıva":          (0.94, 0.93, 0.90),
    "kolon":         (0.76, 0.30, 0.24),
    "perde_asansör": (0.30, 0.69, 0.42),
    "baca":          (0.55, 0.36, 0.68),
    "merdiven":      (0.45, 0.48, 0.52),
    "kapı":          (0.55, 0.35, 0.18),
    "pencere":       (0.95, 0.95, 0.97),
    "cam":           (0.53, 0.78, 0.92),
}


def parse_heights(s: str | None) -> dict[str, float]:
    """``bodrum=300,zemin=320,normal=300`` -> dict (cm)."""
    out: dict[str, float] = {}
    if not s:
        return out
    for tok in s.split(","):
        tok = tok.strip()
        if not tok:
            continue
        if "=" not in tok:
            raise SystemExit(f"--heights biçimi: ad=cm,ad=cm  (alınan: {tok!r})")
        k, v = tok.split("=", 1)
        out[k.strip()] = float(v)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="DXF kat planları -> çok katlı 3B bina")
    ap.add_argument("--dxf", default="data/kavaklik_01.dxf")
    ap.add_argument("--unit", default=None, choices=sorted(dx.UNIT_TO_METRE))
    ap.add_argument("--normal-floors", type=int, default=8,
                    help="normal kat tekrar sayısı (varsayılan 8)")
    ap.add_argument("--heights", default=None,
                    help="kat yükseklikleri cm: bodrum_kat=300,zemin_kat=320,normal_kat=300")
    ap.add_argument("--default-height", type=float, default=300.0,
                    help="--heights ile verilmeyen katlar için yükseklik (cm)")
    ap.add_argument("--slab", type=float, default=30.0,
                    help="asmolen döşeme kalınlığı (cm)")
    ap.add_argument("--plaster", type=float, default=2.0,
                    help="her iki yüzdeki sıva kalınlığı (cm)")
    ap.add_argument("--sill", type=float, default=110.0,
                    help="pencere denizlik yüksekliği (cm)")
    ap.add_argument("--window-height", type=float, default=150.0,
                    help="pencere yüksekliği (cm)")
    ap.add_argument("--door-height", type=float, default=210.0,
                    help="kapı yüksekliği (cm)")
    ap.add_argument("--door-leaf", type=float, default=4.5, help="kapı kanadı (cm)")
    ap.add_argument("--window-frame", type=float, default=10.0, help="doğrama derinliği (cm)")
    ap.add_argument("--glass", type=float, default=1.2, help="cam kalınlığı (cm)")
    ap.add_argument("--min-wall-area", type=float, default=0.02,
                    help="bundan küçük duvar kırpıntısı atılır (m²)")
    ap.add_argument("--no-openings", action="store_true",
                    help="pencere/kapı boşluklarını duvardan ÇIKARMA")
    ap.add_argument("--no-joinery", action="store_true",
                    help="kapı/pencere katılarını ÇİZME")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--out", default="out/bina.glb")
    ap.add_argument("--obj", action="store_true")
    a = ap.parse_args()

    plan = dx.load_plan(a.dxf, unit=a.unit, local_coords=True)
    print(plan.summary())
    print()

    stack = [("bodrum_kat", 1), ("zemin_kat", 1), ("normal_kat", a.normal_floors)]
    stack = [(k, n) for k, n in stack if k in plan.floors]
    if not stack:
        print("Hiç pafta bulunamadı.")
        return 1

    heights = {k: a.default_height for k, _ in stack}
    heights.update(parse_heights(a.heights))

    cfg = cb.Config(
        slab=a.slab / 100.0,
        plaster=a.plaster / 100.0,
        sill=a.sill / 100.0,
        window_height=a.window_height / 100.0,
        door_height=a.door_height / 100.0,
        door_leaf=a.door_leaf / 100.0,
        window_frame=a.window_frame / 100.0,
        glass=a.glass / 100.0,
        min_wall_area=a.min_wall_area,
        openings=not a.no_openings,
        joinery=not a.no_joinery,
    )

    print("Kat şeması:")
    z = 0.0
    for k, n in stack:
        H = heights[k] / 100.0
        print(f"  {k:<14} x{n:<3}  {H:.2f} m   z = {z:6.2f} .. {z + n * H:6.2f} m")
        z += n * H
    print(f"  {'TOPLAM':<14} {sum(n for _, n in stack):<3}  {z:.2f} m")
    print(f"  sıva: her iki yüzde {a.plaster:.0f} cm · döşeme {a.slab:.0f} cm")
    print()

    if a.list:
        return 0

    t0 = time.time()
    print("Katlar üretiliyor...")
    parts, info = cb.build_building(plan, stack, heights, cfg, verbose=True)
    print(f"\n  süre: {time.time() - t0:.1f} sn")

    if not parts:
        print("Hiç gövde üretilmedi.")
        return 1

    meshes = {}
    print(f"\n  {'parça':<16}{'hacim m³':>12}{'üçgen':>10}")
    for name, man in sorted(parts.items()):
        tm = so.to_trimesh(man, color=COLORS.get(name, (0.7, 0.7, 0.7)), name=name)
        if len(tm.faces) == 0:
            continue
        meshes[name] = tm
        print(f"  {name:<16}{man.volume():>12.2f}{len(tm.faces):>10}")

    # modeli orijine yaklaştır (X/Y merkezini 0'a al)
    sc = vw.scene(meshes)
    bb = sc.bounds  # (2, 3)
    if bb is not None and np.isfinite(bb).all():
        cx, cy = (bb[0, 0] + bb[1, 0]) / 2, (bb[0, 1] + bb[1, 1]) / 2
        sc.apply_translation((-cx, -cy, -bb[0, 2]))
        print(f"\n  model orijine alındı (X/Y merkez, Z taban). "
              f"boyut: {bb[1, 0] - bb[0, 0]:.1f} x "
              f"{bb[1, 1] - bb[0, 1]:.1f} x {bb[1, 2] - bb[0, 2]:.1f} m")

    out = Path(a.out)
    vw.export_glb(sc, out)
    print(f"\n GLB  : {out}  ({out.stat().st_size / 1024:.0f} KB)")
    if a.obj:
        print(f" OBJ  : {vw.export_obj(sc, out.with_suffix('.obj'))}")
    legend = {n: "#%02x%02x%02x" % tuple(int(c * 255) for c in COLORS.get(n, (.7,) * 3))
              for n in meshes}
    html = out.with_suffix(".html")
    vw.write_html_viewer(out, html, legend=legend,
                         title=f"{Path(a.dxf).stem} — {info['kat sayısı']} kat")
    print(f" HTML : {html}")
    print(f"\n Toplam yükseklik: {info['toplam yükseklik']:.2f} m · "
          f"{info['kat sayısı']} kat · {len(meshes)} parça")

    # ---- indeks: tüm bina + out/ içindeki tek kat modelleri
    outdir = out.parent
    entries = [(f"{Path(a.dxf).stem} — TÜM BİNA ({info['kat sayısı']} kat)",
                out.name, legend)]
    seen = {out.stem}
    for h in sorted(outdir.glob("*.html")):
        if h.stem == "index" or h.stem in seen:
            continue
        if not (outdir / (h.stem + ".glb")).exists():
            continue
        entries.append((h.stem, h.stem + ".glb", {}))
        seen.add(h.stem)
    lead = (f'<div class="sub" style="padding:14px 30px 0;color:#cfe3f5">'
            f'İlk kart <b>tüm bina</b> — {info["kat sayısı"]} kat, '
            f'{info["toplam yükseklik"]:.1f} m. Altındakiler tek tek kat paftaları.'
            f'</div>')
    idx = vw.write_index(outdir / "index.html", entries,
                         title=f"{Path(a.dxf).stem} — 3B modeller", lead=lead)
    print(f" INDEX : {idx}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
