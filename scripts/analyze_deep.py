#!/usr/bin/env python3
"""kavaklik_01.dxf derin analiz: ic ice bloklar, katman bazli kapali profil
alistirma (flatten), alan istatistikleri ve 3B hatta hazirlik raporu.

Kullanim:
    python scripts/analyze_deep.py data/kavaklik_01.dxf
"""
from __future__ import annotations

import sys
from collections import Counter, defaultdict
from pathlib import Path

import ezdxf
from ezdxf import bbox
from ezdxf.math import Vec3

MM_PER_UNIT = 1.0  # cizim birimi mm gibi gorunuyor (INSUNITS=6 olsa da)


def fmt(v, nd=2):
    return f"{v:,.{nd}f}"


def poly_points(e):
    """LWPOLYLINE/POLYLINE -> [(x, y), ...] (WCS, dünya koordinati)."""
    if e.dxftype() == "LWPOLYLINE":
        return [(p[0], p[1]) for p in e.get_points("xy")]
    if e.dxftype() == "POLYLINE":
        return [(v.dxf.location.x, v.dxf.location.y) for v in e.vertices()]
    return None


def flatten(msp, max_depth=8):
    """INSERT'lari acarak tum geometriyi WCS'ye tasir.

    Donus: (entities, transforms) -> her biri (dxftype, layer, points or None,
    insert_name, matrix)
    """
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
                new_m = m2 if m is None else m @ m2
            except Exception:  # noqa: BLE001
                new_m = m
            for se in blk:
                stack.append((se, new_m, depth + 1))
            continue
        pts = poly_points(e)
        if pts and m is not None:
            pts = [(m.transform(Vec3(x, y, 0)).x, m.transform(Vec3(x, y, 0)).y)
                   for x, y in pts]
        out.append((t, e.dxf.layer, pts, e, m))
    return out


def ring_area(pts):
    """Shoelace (isaretli alan)."""
    n = len(pts)
    if n < 3:
        return 0.0
    s = 0.0
    for i in range(n):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % n]
        s += x1 * y2 - x2 * y1
    return s / 2.0


def ring_perimeter(pts):
    n = len(pts)
    if n < 2:
        return 0.0
    p = 0.0
    for i in range(n):
        if i == n - 1 and pts[0] == pts[-1]:
            break
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % n]
        p += ((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5
    return p


def main(path: str) -> int:
    p = Path(path)
    if not p.exists():
        print(f"Dosya yok: {p}")
        return 1
    doc = ezdxf.readfile(p)
    msp = doc.modelspace()

    print("=" * 86)
    print("DERIN ANALIZ  (INSERT'ler acilmis / WCS)")
    print("=" * 86)

    flat = flatten(msp)
    print(f"\nToplam flatten edilmis entity: {len(flat)}")

    by_type = Counter(t for t, *_ in flat)
    print("\nEntity tipleri (flatten):")
    for t, c in by_type.most_common():
        print(f"  {t:<22}{c:>7}")

    # katman -> flattened sayim
    lay_flat = Counter(l for _, l, *_ in flat)
    print("\nKatman (flatten):")
    for l, c in lay_flat.most_common():
        print(f"  {l:<24}{c:>7}")

    # ---------------------------------------------------------- kapali profil
    print("\n" + "=" * 86)
    print("KAPALI PROFIL ENVANTERI (katman bazinda) - 3B extrude adayi")
    print("=" * 86)
    print(f"{'Katman':<18}{'Kapali':>7}{'Acik':>7}{'Nokta':>8}"
          f"{'Alan top (m2)':>16}{'Alan min':>10}{'Alan max':>12}")
    per_layer = defaultdict(list)
    open_count = Counter()
    pt_count = Counter()
    for t, layer, pts, e, m in flat:
        if t not in ("LWPOLYLINE", "POLYLINE"):
            continue
        pt_count[layer] += len(pts)
        try:
            closed = bool(e.closed)
        except Exception:  # noqa: BLE001
            closed = pts[0] == pts[-1]
        if closed and len(pts) >= 3:
            per_layer[layer].append(abs(ring_area(pts)) / 1e6)
        else:
            open_count[layer] += 1

    for layer in sorted(per_layer, key=lambda l: -len(per_layer[l])):
        areas = per_layer[layer]
        tot = sum(areas)
        print(f"{layer:<18}{len(areas):>7}{open_count[layer]:>7}{pt_count[layer]:>8}"
              f"{fmt(tot, 1):>16}{fmt(min(areas), 2):>10}{fmt(max(areas), 2):>12}")

    tot_closed = sum(len(v) for v in per_layer.values())
    print(f"\nTOPLAM kapali profil: {tot_closed}")
    print(f"TOPLAM kapali alan  : {fmt(sum(sum(v) for v in per_layer.values()), 1)} m2"
          "  (ust uste binen kat bloklari dahil)")

    # ---------------------------------------------------------- kat bloklari
    print("\n" + "=" * 86)
    print("KAT BLOKLARI (bodrum / zemin / normal) - kendi ic sinirlari")
    print("=" * 86)
    for blk_name in ("bodrum_kat", "zemin_kat", "normal_kat"):
        try:
            blk = doc.blocks.get(blk_name)
        except Exception:  # noqa: BLE001
            print(f"  {blk_name}: yok")
            continue
        ents = list(blk)
        try:
            eb = bbox.extents(ents)
            mn, mx = eb.extmin, eb.extmax
            dims = f"{fmt(mx.x-mn.x)} x {fmt(mx.y-mn.y)} mm  " \
                   f"(X {fmt(mn.x)}..{fmt(mx.x)}, Y {fmt(mn.y)}..{fmt(mx.y)})"
        except Exception as ex:  # noqa: BLE001
            dims = f"sinir yok ({ex})"
        lay = Counter(e.dxf.layer for e in ents)
        closed_in = sum(1 for e in ents if e.dxftype() in ("LWPOLYLINE", "POLYLINE")
                        and getattr(e, "closed", False))
        print(f"\n  {blk_name}: {len(ents)} entity, kapali polyline {closed_in}")
        print(f"    sinir: {dims}")
        print(f"    katmanlar: {dict(lay)}")

    # insert konumlari
    print("\n  INSERT konumlari (modelspace):")
    for e in msp.query("INSERT"):
        try:
            pos = e.dxf.insert
            print(f"    {e.dxf.name:<16} @ ({fmt(pos.x)}, {fmt(pos.y)}, {fmt(pos.z)})"
                  f"  rot={getattr(e.dxf, 'rotation', 0):.1f}"
                  f"  scale=({e.dxf.xscale:.2f},{e.dxf.yscale:.2f},{e.dxf.zscale:.2f})")
        except Exception:  # noqa: BLE001
            pass

    # ---------------------------------------------------------- kolon / kapi
    print("\n" + "=" * 86)
    print("KOLON (C_kolon) VE KAPI (C_kapi) DETAYI")
    print("=" * 86)
    col_shapes = Counter()
    for t, layer, pts, e, m in flat:
        if layer == "C_kolon" and pts and len(pts) >= 3:
            xs = [q[0] for q in pts]
            ys = [q[1] for q in pts]
            w, h = max(xs) - min(xs), max(ys) - min(ys)
            col_shapes[(round(min(w, h), 1), round(max(w, h), 1), len(pts))] += 1
    print("\nKolon kesit olculeri (kisa kenar, uzun kenar, nokta sayisi) -> adet:")
    for k, c in sorted(col_shapes.items(), key=lambda kv: -kv[1])[:20]:
        print(f"  {k[0]:>7.1f} x {k[1]:<7.1f} ({k[2]} nokta)  -> {c:>4} adet")

    door_blocks = Counter()
    for e in msp.query("INSERT"):
        if e.dxf.layer == "C_kapi":
            door_blocks[e.dxf.name] += 1
    print("\nKapi blogu dagilimi:", dict(door_blocks))

    win_sizes = Counter()
    for t, layer, pts, e, m in flat:
        if layer == "C_pencere" and pts:
            xs = [q[0] for q in pts]
            ys = [q[1] for q in pts]
            win_sizes[(round(max(xs) - min(xs)), round(max(ys) - min(ys)))] += 1
    print("\nPencere gabari olculeri (dx x dy) -> adet (ilk 15):")
    for k, c in sorted(win_sizes.items(), key=lambda kv: -kv[1])[:15]:
        print(f"  {k[0]:>6} x {k[1]:<6} -> {c:>3}")

    # ---------------------------------------------------------- oda adlari
    print("\n" + "=" * 86)
    print("ODA / MEKAN ADLARI (mekanadi katmani)")
    print("=" * 86)
    rooms = []
    for e in msp.query("MTEXT"):
        if e.dxf.layer == "mekanadi":
            txt = e.text.replace("\\P", " ").replace("\n", " ").strip()
            rooms.append((round(e.dxf.insert.x), round(e.dxf.insert.y), txt))
    for x, y, t in sorted(rooms, key=lambda r: (-r[1], r[0])):
        print(f"  ({x:>6}, {y:>6})  {t}")

    # ---------------------------------------------------------- TEXT (0 katmani)
    print("\n" + "=" * 86)
    print("SERBEST METINLER (katman 0)")
    print("=" * 86)
    for e in msp.query("TEXT"):
        if e.dxf.layer == "0":
            pos = e.dxf.insert
            print(f"  ({fmt(pos.x,0):>7}, {fmt(pos.y,0):>7})  h={e.dxf.height:.0f}  {e.dxf.text}")

    # ---------------------------------------------------------- CIRCLE
    print("\n" + "=" * 86)
    print("DAIRELER (CIRCLE) - 32 adet, muhtemel kolon/tesisat sembolu")
    print("=" * 86)
    rr = Counter()
    for e in msp.query("CIRCLE"):
        rr[round(e.dxf.radius, 1)] += 1
    for r, c in sorted(rr.items(), key=lambda kv: -kv[1]):
        print(f"  r={r:>8.1f} mm  -> {c:>3} adet")

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "data/kavaklik_01.dxf"))
