#!/usr/bin/env python3
"""Bir kat paftasını 3B katı modele çevirir (uçtan uca hat).

    ezdxf -> (INSERT açma) -> shapely (temizlik/boolean) -> manifold3d (CSG)
          -> trimesh (sahne) -> .glb + three.js HTML izleyici

Kullanim:
    python scripts/build3d.py --dxf data/kavaklik_01.dxf --floor normal_kat
    python scripts/build3d.py --list            # paftalari listele
    python scripts/build3d.py --floor zemin_kat --wall-height 320 --openings
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import numpy as np  # noqa: E402

import cad2d.dxfio as dx  # noqa: E402
import cad2d.solid as so  # noqa: E402
import cad2d.view as vw  # noqa: E402

# parça adı -> (katmanlar, renk)
PARTS: dict[str, tuple[tuple[str, ...], tuple[float, float, float]]] = {
    "döseme":   (("Bina_kontur",),            (0.62, 0.62, 0.65)),
    "duvar":    (("__walls__",),              (0.86, 0.85, 0.80)),
    "kolon":    (("C_kolon",),                (0.76, 0.30, 0.24)),
    "balkon":   (("B_balkon",),               (0.20, 0.66, 0.55)),
    "asansör":  (("Asansör",),                (0.30, 0.69, 0.42)),
    "baca":     (("C_baca", "HavaBaca"),      (0.55, 0.36, 0.68)),
    "merdiven": (("Merdiven", "Merd+Koridor"), (0.45, 0.48, 0.52)),
}

# duvar boşluğu (iç mekân) olarak kullanılacak katmanlar
VOID_LAYERS = ("C_oda", "Merdiven", "Merd+Koridor", "Asansör", "C_baca",
               "HavaBaca", "C_kapi")


def build_floor(floor: dx.Floor, unit_to_metre: float, a) -> dict:
    """Bir katın parça sözlüğünü (ad -> trimesh) üretir."""
    t0 = time.time()
    rings = floor.rings
    m_per_unit = unit_to_metre
    wall_h = a.wall_height / 100.0
    slab_h = a.slab / 100.0
    sill = a.sill / 100.0
    win_h = a.window_height / 100.0
    door_h = a.door_height / 100.0

    meshes: dict[str, object] = {}
    stats: list[tuple[str, float, int]] = []   # (ad, hacim m³, üçgen)

    def add(name: str, man, color):
        if man.is_empty():
            print(f"  ! {name}: boş gövde, atlandı")
            return
        if not so.status_ok(man):
            print(f"  ! {name}: manifold durumu {man.status()} (yine de deneniyor)")
        tm = so.to_trimesh(man, color=color, name=name)
        if len(tm.faces) == 0:
            print(f"  ! {name}: üçgen yok, atlandı")
            return
        meshes[name] = tm
        stats.append((name, float(man.volume()), len(tm.faces)))

    # ---------------------------------------------------------- döşeme
    slab_polys = so.union_polygons(
        so.to_polygons(floor.layer("Bina_kontur"), m_per_unit))
    if slab_polys:
        man = so.extrude(slab_polys, slab_h).translate((0, 0, -slab_h))
        add("döseme", man, PARTS["döseme"][1])

    # ---------------------------------------------------------- duvarlar
    contour = floor.layer("Bina_kontur")
    voids = [r for lyr in VOID_LAYERS for r in floor.layer(lyr)]
    if contour:
        try:
            walls, wall_polys = so.walls_from_contour(
                contour, voids, z0=0.0, height=wall_h,
                unit_to_metre=m_per_unit, min_wall_area=a.min_wall_area)
            wa = sum(p.area for p in wall_polys)
            print(f"  duvar poligonu: {len(wall_polys)} parça, {wa:.1f} m² taban alanı")

            if a.openings:
                walls = carve_openings(walls, floor, m_per_unit,
                                       sill, win_h, door_h, a)
            add("duvar", walls, PARTS["duvar"][1])
        except ValueError as e:
            print(f"  ! duvar üretilemedi: {e}")

    # ---------------------------------------------------------- diğerleri
    for part, (layers, color) in PARTS.items():
        if part in ("döseme", "duvar"):
            continue
        rs = [r for lyr in layers for r in floor.layer(lyr)]
        if not rs:
            continue
        polys = so.union_polygons(so.to_polygons(rs, m_per_unit))
        if not polys:
            continue
        h = wall_h if part in ("kolon", "asansör", "baca") else slab_h * 2
        z0 = 0.0
        man = so.extrude(polys, h).translate((0, 0, z0))
        add(part, man, color)

    print(f"  süre: {time.time() - t0:.2f} sn")
    print(f"  {'parça':<12}{'hacim m³':>12}{'üçgen':>10}")
    for name, vol, tri in stats:
        print(f"  {name:<12}{vol:>12.2f}{tri:>10}")
    return meshes


def carve_openings(walls, floor: dx.Floor, m_per_unit: float,
                   sill: float, win_h: float, door_h: float, a):
    """Pencere ve kapı boşluklarını duvardan CSG ile çıkarır."""
    import shapely
    from shapely.ops import unary_union

    # --- pencereler: C_pencere dikdörtgenleri, sill..sill+win_h
    win = so.union_polygons(so.to_polygons(floor.layer("C_pencere"), m_per_unit))
    if win:
        # yalnızca duvarla gerçekten kesişenleri kullan
        wm = so.extrude(win, win_h).translate((0, 0, sill))
        before = walls.volume()
        walls = walls - wm
        print(f"  pencere boşluğu: {len(win)} adet, "
              f"-{before - walls.volume():.2f} m³")
    # --- kapılar: kp_* bloklarının eşik dolgusu (dvr_kaba) + C_kapi
    door = so.union_polygons(
        so.to_polygons(floor.layer("dvr_kaba") + floor.layer("C_kapi"),
                       m_per_unit))
    if door:
        dm = so.extrude(door, door_h)
        before = walls.volume()
        walls = walls - dm
        print(f"  kapı boşluğu   : {len(door)} adet, "
              f"-{before - walls.volume():.2f} m³")
    return walls


def main() -> int:
    ap = argparse.ArgumentParser(description="DXF kat planı -> 3B katı model")
    ap.add_argument("--dxf", default="data/kavaklik_01.dxf")
    ap.add_argument("--floor", default=None,
                    help="pafta adı (varsayılan: ilk pafta)")
    ap.add_argument("--list", action="store_true", help="paftaları listele ve çık")
    ap.add_argument("--unit", default=None, choices=sorted(dx.UNIT_TO_METRE),
                    help="çizim birimi (varsayılan: otomatik)")
    ap.add_argument("--wall-height", type=float, default=300.0,
                    help="kat yüksekliği (cm)")
    ap.add_argument("--slab", type=float, default=20.0,
                    help="döşeme kalınlığı (cm)")
    ap.add_argument("--sill", type=float, default=90.0,
                    help="pencere denizlik yüksekliği (cm)")
    ap.add_argument("--window-height", type=float, default=150.0,
                    help="pencere yüksekliği (cm)")
    ap.add_argument("--door-height", type=float, default=210.0,
                    help="kapı yüksekliği (cm)")
    ap.add_argument("--min-wall-area", type=float, default=0.05,
                    help="bundan küçük duvar parçaları atılır (m²)")
    ap.add_argument("--openings", action="store_true",
                    help="pencere/kapı boşluklarını duvardan çıkar (CSG)")
    ap.add_argument("--local", action="store_true",
                    help="koordinatları pafta sol-alt köşesine göre kaydır")
    ap.add_argument("--all", action="store_true",
                    help="tüm paftaları ayrı ayrı üret (+ index.html)")
    ap.add_argument("--out", default="out/model.glb")
    ap.add_argument("--html", default=None,
                    help="three.js HTML izleyici (varsayılan: <out>.html)")
    ap.add_argument("--obj", action="store_true", help="ayrıca .obj yaz")
    a = ap.parse_args()

    plan = dx.load_plan(a.dxf, unit=a.unit, local_coords=a.local)
    print(plan.summary())
    print()

    if a.list or not plan.floors:
        if not plan.floors:
            print("Hiç pafta bulunamadı.")
        return 0

    if a.floor and a.floor not in plan.floors:
        print(f"'{a.floor}' bulunamadı. Mevcut paftalar: {list(plan.floors)}")
        return 1
    names = list(plan.floors) if (a.all or not a.floor) else [a.floor]
    if not a.all:
        names = names[:1]

    print(f"    kat yüksekliği {a.wall_height:.0f} cm, "
          f"döşeme {a.slab:.0f} cm, birim = 1 {plan.unit}")
    print()

    built: list[tuple[str, str, dict]] = []
    outdir = Path(a.out).parent
    for name in names:
        floor = plan.floors[name]
        print(f">>> {name}: {len(floor.rings)} ring, {floor.title or '(başlıksız)'}")
        meshes = build_floor(floor, plan.unit_to_metre, a)
        print()
        if not meshes:
            print("  hiç gövde üretilemedi, atlanıyor\n")
            continue

        sc = vw.scene(meshes)
        out = outdir / f"{name}.glb" if (a.all or len(names) > 1) else Path(a.out)
        vw.export_glb(sc, out)
        print(f"  GLB  : {out}  ({out.stat().st_size / 1024:.0f} KB)")
        if a.obj:
            print(f"  OBJ  : {vw.export_obj(sc, out.with_suffix('.obj'))}")

        legend = {p: "#%02x%02x%02x" % tuple(int(c * 255) for c in col)
                  for p, (_l, col) in PARTS.items() if p in meshes}
        html = Path(a.html) if (a.html and len(names) == 1) else out.with_suffix(".html")
        vw.write_html_viewer(out, html, legend=legend,
                             title=f"{Path(a.dxf).stem} — {name}", grid=100)
        print(f"  HTML : {html}\n")
        built.append((name, out.name, legend))

    if not built:
        return 1
    if len(built) > 1:
        idx = vw.write_index(outdir / "index.html", built,
                             title=f"{Path(a.dxf).stem} — kat paftaları")
        print(f" INDEX : {idx}  ({len(built)} pafta)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
