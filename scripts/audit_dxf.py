#!/usr/bin/env python3
"""kavaklik_01.dxf yapisal analizi (ezdxf).

Kullanim:
    python scripts/audit_dxf.py data/kavaklik_01.dxf
"""
from __future__ import annotations

import sys
from collections import Counter, defaultdict
from pathlib import Path

import ezdxf
from ezdxf import bbox


def fmt(v, nd=3):
    return f"{v:.{nd}f}"


def main(path: str) -> int:
    p = Path(path)
    if not p.exists():
        print(f"Dosya yok: {p}")
        return 1

    print("=" * 78)
    print(f"DOSYA : {p.name}  ({p.stat().st_size / 1024:.1f} KB)")
    print("=" * 78)

    try:
        doc = ezdxf.readfile(p)
    except IOError as e:
        print(f"DXF okunamadi (IO): {e}")
        return 1
    except ezdxf.DXFStructureError as e:
        print(f"DXF bozuk/yapilandirma hatasi: {e}")
        return 1

    hdr = doc.header
    print(f"\nDXF SURUMU      : {doc.dxfversion}  ({doc.acad_release})")
    print(f"Birim (INSUNITS): {hdr.get('$INSUNITS', 'tanimsiz')}"
          "   (6 = metre, 4 = mm, 1 = inch)")
    print(f"$MEASUREMENT    : {hdr.get('$MEASUREMENT', 'tanimsiz')} (0=Imperial, 1=Metric)")
    print(f"Linetype olcegi : {hdr.get('$LTSCALE', '?')}   Psltscale: {hdr.get('$PSLTSCALE', '?')}")
    print(f"UCS/EXTRUSION   : okunabilir, asagida entity bazinda")
    print(f"Kaydeden uyg.   : {hdr.get('$FINGERPRINTGUID', '')[:0]}"
          f"{doc.header.get('$LASTSAVEDBY', 'bilinmiyor')}")

    # ---------------------------------------------------------------- layers
    print("\n" + "-" * 78)
    print("KATMANLAR (LAYER)")
    print("-" * 78)
    layer_counts: Counter[str] = Counter()
    layer_types: dict[str, Counter] = defaultdict(Counter)
    layer_geom: dict[str, Counter] = defaultdict(Counter)

    msp = doc.modelspace()
    for e in msp:
        layer_counts[e.dxf.layer] += 1
        layer_types[e.dxf.layer][e.dxftype()] += 1

    print(f"{'Katman':<28}{'Adet':>8}  {'Entity tipleri'}")
    for name, cnt in layer_counts.most_common():
        types = ", ".join(f"{t}x{c}" for t, c in layer_types[name].most_common())
        print(f"{name:<28}{cnt:>8}  {types[:90]}")

    print(f"\nToplam entity (modelspace): {sum(layer_counts.values())}")
    print(f"Toplam katman             : {len(layer_counts)}")

    # --------------------------------------------------------------- blocks
    print("\n" + "-" * 78)
    print("BLOKLAR (BLOCK / INSERT)")
    print("-" * 78)
    blk_rows = []
    for b in doc.blocks:
        n = len(b)
        et = Counter(e.dxftype() for e in b)
        blk_rows.append((b.name, n, ", ".join(f"{t}x{c}" for t, c in et.most_common(6))))
    anon = [r for r in blk_rows if r[0].startswith("*")]
    named = [r for r in blk_rows if not r[0].startswith("*")]
    print(f"Blok sayisi: {len(blk_rows)}  (isimli: {len(named)}, anonim *D/*U/*T: {len(anon)})")
    for name, n, et in sorted(named, key=lambda r: -r[1])[:40]:
        print(f"  {name:<32}{n:>6}  {et[:70]}")
    inserts = Counter()
    for e in msp.query("INSERT"):
        inserts[e.dxf.name] += 1
    if inserts:
        print("\nINSERT dagilimi (modelspace):")
        for name, c in inserts.most_common(40):
            print(f"  {name:<32}{c:>6}")
    else:
        print("\nModelspace'te INSERT yok.")

    # --------------------------------------------------------------- extents
    print("\n" + "-" * 78)
    print("SINIRLAR (BOUNDING BOX) - modelspace")
    print("-" * 78)
    try:
        ext = bbox.extents(msp)
        if ext.has_data:
            mn, mx = ext.extmin, ext.extmax
            print(f"X: {fmt(mn.x)} .. {fmt(mx.x)}   (genislik {fmt(mx.x - mn.x)})")
            print(f"Y: {fmt(mn.y)} .. {fmt(mx.y)}   (yukseklik {fmt(mx.y - mn.y)})")
            print(f"Z: {fmt(mn.z)} .. {fmt(mx.z)}   (derinlik {fmt(mx.z - mn.z)})")
        else:
            print("Sinir hesaplanamadi.")
    except Exception as e:  # noqa: BLE001
        print(f"Sinir hesaplanamadi: {e}")

    print("\nEXTMIN/EXTMAX (header):", hdr.get("$EXTMIN", "?"), hdr.get("$EXTMAX", "?"))

    # ------------------------------------------------- geometry census
    print("\n" + "-" * 78)
    print("GEOMETRI SAYIMI (kapali profil adaylari)")
    print("-" * 78)
    closed_polys = 0
    open_polys = 0
    lw_pts = 0
    hatch_count = 0
    ellipse_like = 0
    for e in msp:
        t = e.dxftype()
        if t in ("LWPOLYLINE", "POLYLINE"):
            if e.closed:
                closed_polys += 1
            else:
                open_polys += 1
            try:
                lw_pts += len(list(e.vertices())) if t == "POLYLINE" else len(e)
            except Exception:  # noqa: BLE001
                pass
        elif t == "HATCH":
            hatch_count += 1
        elif t in ("CIRCLE", "ARC", "ELLIPSE"):
            ellipse_like += 1
    print(f"Kapali polyline   : {closed_polys}")
    print(f"Acik polyline     : {open_polys}")
    print(f"Polyline toplam nokta: {lw_pts}")
    print(f"HATCH             : {hatch_count}")
    print(f"CIRCLE/ARC/ELLIPSE: {ellipse_like}")

    # ------------------------------------------------- entity tip dagilimi
    print("\n" + "-" * 78)
    print("ENTITY TIP DAGILIMI (modelspace)")
    print("-" * 78)
    tc = Counter(e.dxftype() for e in msp)
    for t, c in tc.most_common():
        print(f"  {t:<24}{c:>8}")

    # ------------------------------------------------- paperspace / text
    print("\n" + "-" * 78)
    print("DIGER")
    print("-" * 78)
    print(f"Layout sayisi      : {len(doc.layouts)} -> "
          f"{[l.name for l in doc.layouts]}")
    txt = list(msp.query("TEXT MTEXT ATTRIB"))
    print(f"Metin entity       : {len(txt)}")
    dims = list(msp.query("DIMENSION"))
    print(f"Olculendirme       : {len(dims)}")
    print(f"Kayitli APPID'ler  : {[a.dxf.name for a in doc.appids][:10]}")
    print(f"LineType sayisi    : {len(doc.linetypes)}")
    print(f"TextStyle sayisi   : {len(doc.styles)}")

    # ------------------------------------------------- 3B uyari
    print("\n" + "-" * 78)
    print("3B'YE DONUSTURME ACISINDAN DEGERLENDIRME")
    print("-" * 78)
    zvals = set()
    for e in msp:
        try:
            if e.dxftype() == "LWPOLYLINE":
                zvals.add(round(e.dxf.elevation, 6))
            elif hasattr(e.dxf, "extrusion"):
                pass
        except Exception:  # noqa: BLE001
            pass
    print(f"LWPOLYLINE elevation degerleri: {sorted(zvals)[:10]}"
          f"{' ...' if len(zvals) > 10 else ''}")
    print("Not: 2B DXF -> 3B icin ezdxf (okuma) + shapely (poligon/Boolean)")
    print("     + manifold3d (extrude/CSG) + trimesh (gorsellestirme) hatti kullanilacak.")

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "data/kavaklik_01.dxf"))
