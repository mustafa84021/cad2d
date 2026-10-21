"""Çok katlı bina modeli: kat istifleme, sıva katmanı, kapı/pencere katıları.

Sıva geleneği (kavaklik_01.dxf'teki ``kp_*`` kapı bloklarından okundu)::

    kp_90      dvr_kaba  90 x 15   ->   dvr_siva  86 x 19
    kp_90_20   dvr_kaba  90 x 20   ->   dvr_siva  86 x 24
    kp_90_10   dvr_kaba  90 x 10   ->   dvr_siva  86 x 14

Yani **her iki yüzde 2 cm sıva**: boşluk eni 4 cm daralır, duvar kalınlığı
4 cm artar.  Bu modül aynı kuralı 3B'de uygular:

    sıvalı duvar  = Bina_kontur − iç mekânlar      (odalar net yüzeye çizilir)
    kaba duvar    = sıvalı duvar.buffer(−2 cm)     (sıvayı soymak)
    sıva kabuğu   = sıvalı duvar − kaba duvar      (2 cm kılıf)
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import shapely
from shapely.geometry import Polygon, box
from shapely.ops import unary_union

from . import solid as so
from .dxfio import Floor

#: Her iki yüzdeki sıva kalınlığı (metre)
PLASTER = 0.02

__all__ = ["PLASTER", "Config", "wall_layers", "rect_thin", "rect_deepen",
           "build_storey", "build_building", "DEFAULT_STACK"]


def _flat(g) -> list[Polygon]:
    return so._flatten_polygons(g)


# ------------------------------------------------------------------ dikdörtgen
def as_rect(poly: Polygon, tol: float = 0.02):
    """Eksen hizalı dikdörtgeni ``(minx, miny, maxx, maxy)`` döndürür, değilse None."""
    minx, miny, maxx, maxy = poly.bounds
    ba = (maxx - minx) * (maxy - miny)
    if ba <= 0:
        return None
    if poly.area / ba < 1.0 - tol:
        return None
    return (minx, miny, maxx, maxy)


def rect_thin(poly: Polygon, thickness: float) -> Polygon:
    """Dikdörtgeni **kısa ekseninde** inceltir (kapı kanadı / pencere camı).

    Örn. 90 × 15 cm kapı boşluğu + 4.5 cm kanat -> 90 × 4.5 cm.
    """
    r = as_rect(poly)
    if r is None:
        e = poly.buffer(-thickness / 2, join_style=2)
        return e if not e.is_empty else poly
    minx, miny, maxx, maxy = r
    w, h = maxx - minx, maxy - miny
    cx, cy = (minx + maxx) / 2.0, (miny + maxy) / 2.0
    if w <= h:                      # kısa eksen = X
        return box(cx - thickness / 2, miny, cx + thickness / 2, maxy)
    return box(minx, cy - thickness / 2, maxx, cy + thickness / 2)


def rect_deepen(poly: Polygon, target: float = 0.45, extra: float = 0.30) -> Polygon:
    """Boşluğu **kısa ekseninde** büyütür; duvarı tam delsin diye.

    Kapı bloğu 15 cm derinlikle çizilmiş olabilir ama gerçek duvar 20 cm
    olabilir.  Boşluğu derinlik ekseninde ``max(target, derinlik + extra)``
    kadar uzatıp duvardan çıkarınca tam geçen bir delik elde edilir;
    **uzunluk ekseni bozulmaz** (kapı/pencere genişliği korunur).
    """
    r = as_rect(poly)
    if r is None:
        return poly.buffer(extra, join_style=2)
    minx, miny, maxx, maxy = r
    w, h = maxx - minx, maxy - miny
    cx, cy = (minx + maxx) / 2.0, (miny + maxy) / 2.0
    if w <= h:                      # kısa eksen = X
        d = max(target, w + extra)
        return box(cx - d / 2, miny - 0.02, cx + d / 2, maxy + 0.02)
    d = max(target, h + extra)
    return box(minx - 0.02, cy - d / 2, maxx + 0.02, cy + d / 2)


# ------------------------------------------------------------------ sıva
def wall_layers(
    siva_polys: list[Polygon],
    plaster: float = PLASTER,
    min_area: float = 1e-4,
) -> tuple[list[Polygon], list[Polygon]]:
    """Sıvalı duvar poligonlarını **kaba duvar** ve **sıva kabuğu** olarak ayırır.

    Returns:
        (kaba_polys, siva_kabuk_polys)

    Not: kalınlığı 2 × plaster'dan (4 cm) ince olan duvar parçaları tamamen
    sıva sayılır — kaba duvar listesine girmez.
    """
    kaba: list[Polygon] = []
    for p in siva_polys:
        if p.area <= 0:
            continue
        eroded = p.buffer(-plaster, join_style=2)
        if eroded.is_empty:
            continue
        for q in _flat(eroded):
            if q.area >= min_area:
                kaba.append(q)
    if not kaba:
        return [], [p for p in siva_polys if p.area >= min_area]
    shell = _flat(unary_union(siva_polys).difference(unary_union(kaba)))
    shell = [p for p in shell if p.area >= min_area]
    return kaba, shell


def shell_polys(polys: list[Polygon], thickness: float) -> list[Polygon]:
    """İçi boş şaft / perde duvarı: dışa ``thickness`` genişlet, içini çıkar.

    Asansör kuyusu, baca ve hava bacası planlarda **boşluk** olarak çizilir.
    Bunları katı olarak extrude etmek kuyuyu doldurur; doğrusu etrafına
    perde duvarı örmektir.
    """
    if not polys:
        return []
    outer = so.union_polygons([p.buffer(thickness, join_style=2) for p in polys])
    inner = so.union_polygons(polys)
    if not outer or not inner:
        return []
    ring = _flat(unary_union(outer).difference(unary_union(inner)))
    return [p for p in ring if p.area >= 1e-4]


def stair_polys(
    rings,
    unit_to_metre: float,
    z0: float,
    rise_total: float,
    tread_depth: float = 0.28,
    tread_thickness: float = 0.18,
    landing_thickness: float = 0.20,
) -> list[tuple[list[Polygon], float, float]]:
    """Merdiven planından basamak / sahanlık dilimleri üretir.

    ``C_merdiven`` katmanında uçuşlar dikdörtgen hâlinde çizilidir.
    Uzun kenarı ≥ 2.0 m ve kısa kenarı ≤ 1.6 m olanlar **uçuş** sayılır ve
    ``tread_depth`` adımda basamaklara bölünerek ``rise_total`` kadar
    yükselir; diğerleri **sahanlık** (yatay plak) olur.

    Returns:
        ``[(poligonlar, z, kalınlık), ...]``
    """
    slabs: list[tuple[list[Polygon], float, float]] = []
    polys = so.union_polygons(so.to_polygons(rings, unit_to_metre))
    for p in polys:
        if p.area < 0.10:
            continue
        r = as_rect(p)
        if r is None:
            slabs.append(([p], z0, landing_thickness))
            continue
        minx, miny, maxx, maxy = r
        w, h = maxx - minx, maxy - miny
        long_side, short_side = max(w, h), min(w, h)
        if long_side >= 2.0 and short_side <= 1.6:
            n = max(2, int(round(long_side / tread_depth)))
            rise = rise_total / n
            if w >= h:                       # uzun eksen = X
                x0, step = minx, w / n
                for i in range(n):
                    strip = box(x0 + i * step, miny, x0 + (i + 1) * step, maxy)
                    slabs.append(([strip], z0 + i * rise, tread_thickness))
            else:                            # uzun eksen = Y
                y0, step = miny, h / n
                for i in range(n):
                    strip = box(minx, y0 + i * step, maxx, y0 + (i + 1) * step)
                    slabs.append(([strip], z0 + i * rise, tread_thickness))
        else:
            slabs.append(([p], z0 + rise_total, landing_thickness))
    return slabs


# ------------------------------------------------------------------ ayarlar
@dataclass
class Config:
    """Bina üretim ayarları (tüm uzunluklar metre)."""

    slab: float = 0.30            # asmolen döşeme kalınlığı
    plaster: float = PLASTER      # her iki yüzde sıva
    sill: float = 1.10            # pencere denizlik yüksekliği
    window_height: float = 1.50   # pencere yüksekliği
    door_height: float = 2.10     # kapı yüksekliği
    door_leaf: float = 0.045      # kapı kanadı kalınlığı
    window_frame: float = 0.10    # pencere doğrama derinliği
    glass: float = 0.012          # cam kalınlığı
    min_wall_area: float = 0.02   # m² — bundan küçük duvar kırpıntısı atılır
    openings: bool = True         # pencere/kapı boşluklarını duvardan çıkar
    joinery: bool = True          # kapı/pencere katılarını çiz
    stairs: bool = True           # merdiven basamaklarını çiz
    shaft_wall: float = 0.10      # asansör/baca perde duvarı kalınlığı
    void_layers: tuple[str, ...] = ("C_oda", "Merdiven", "Merd+Koridor",
                                    "Asansör", "C_baca", "HavaBaca", "C_kapi")


#: (pafta adı, tekrar sayısı) — bodrum + zemin + 8 normal kat
DEFAULT_STACK: list[tuple[str, int]] = [
    ("bodrum_kat", 1),
    ("zemin_kat", 1),
    ("normal_kat", 8),
]


# ------------------------------------------------------------------ tek kat
def build_storey(
    floor: Floor,
    unit_to_metre: float,
    z_base: float,
    height: float,
    cfg: Config,
) -> dict[str, "object"]:
    """Bir katın katı gövdelerini üretir.

    Kat dikey şeması::

        z_base ──────────── döşeme altı
        z_base + slab  ─── döşeme üstü / duvar tabanı
        z_base + height ── duvar tepesi (üst katın döşemesi buraya oturur)

    Returns:
        {parça adı: manifold3d.Manifold}
    """
    u = unit_to_metre
    out: dict[str, object] = {}
    z_wall = z_base + cfg.slab
    h_wall = max(height - cfg.slab, 0.10)

    def put(name, man):
        if man is None or man.is_empty():
            return
        if len(np.asarray(man.to_mesh().tri_verts)) == 0:
            return
        out[name] = man

    # ---------------------------------------------------------- döşeme
    slab_polys = so.union_polygons(so.to_polygons(
        floor.layer("Bina_kontur") + floor.layer("B_balkon"), u))
    if slab_polys:
        put("döseme", so.extrude(slab_polys, cfg.slab).translate((0, 0, z_base)))

    # ---------------------------------------------------------- duvar
    contours = floor.layer("Bina_kontur")
    voids = [r for lyr in cfg.void_layers for r in floor.layer(lyr)]
    siva_polys: list[Polygon] = []
    if contours:
        try:
            siva_polys = so.wall_polys(contours, voids, u, cfg.min_wall_area)
        except ValueError as e:
            print(f"    ! duvar: {e}")
            siva_polys = []

    kaba_polys, plaster_polys = wall_layers(siva_polys, cfg.plaster)

    # boşluk prizmaları (duvardan çıkarılacak)
    win_prism = door_prism = None
    if cfg.openings and (kaba_polys or shell_polys):
        win = [rect_deepen(p) for p in
               so.union_polygons(so.to_polygons(floor.layer("C_pencere"), u))]
        win = so.union_polygons([p for p in win if p and not p.is_empty])
        if win:
            win_prism = so.extrude(win, cfg.window_height).translate(
                (0, 0, z_wall + cfg.sill))
        door = [rect_deepen(p) for p in
                so.union_polygons(so.to_polygons(
                    floor.layer("dvr_kaba") + floor.layer("C_kapi"), u))]
        door = so.union_polygons([p for p in door if p and not p.is_empty])
        if door:
            door_prism = so.extrude(door, cfg.door_height).translate((0, 0, z_wall))

    def carve(m):
        if win_prism is not None:
            m = m - win_prism
        if door_prism is not None:
            m = m - door_prism
        return m

    if kaba_polys:
        put("duvar_kaba", carve(
            so.extrude(kaba_polys, h_wall).translate((0, 0, z_wall))))
    if plaster_polys:
        put("sıva", carve(
            so.extrude(plaster_polys, h_wall).translate((0, 0, z_wall))))

    # ---------------------------------------------------------- kapı/pencere
    if cfg.joinery:
        d = so.union_polygons(so.to_polygons(
            floor.layer("dvr_kaba") + floor.layer("C_kapi"), u))
        if d:
            leaves = so.union_polygons(
                [p for p in (rect_thin(q, cfg.door_leaf) for q in d)
                 if p and not p.is_empty])
            if leaves:
                put("kapı", so.extrude(leaves, cfg.door_height).translate(
                    (0, 0, z_wall)))
        w = so.union_polygons(so.to_polygons(floor.layer("C_pencere"), u))
        if w:
            frames = so.union_polygons(
                [p for p in (rect_thin(q, cfg.window_frame) for q in w)
                 if p and not p.is_empty])
            if frames:
                put("pencere", so.extrude(frames, cfg.window_height).translate(
                    (0, 0, z_wall + cfg.sill)))
            panes = so.union_polygons(
                [p for p in (rect_thin(q, cfg.glass) for q in w)
                 if p and not p.is_empty])
            if panes:
                put("cam", so.extrude(panes, cfg.window_height * 0.9).translate(
                    (0, 0, z_wall + cfg.sill + cfg.window_height * 0.05)))

    # ---------------------------------------------------------- kolon (katı)
    cols = so.union_polygons(so.to_polygons(floor.layer("C_kolon"), u))
    if cols:
        put("kolon", so.extrude(cols, h_wall).translate((0, 0, z_wall)))

    # ------------------------------------------ şaft perdeleri (içi BOŞ halka)
    # Asansör / baca / hava bacası planlarda boşluktur: katı extrude etmek
    # kuyuyu doldurur.  Doğrusu etrafına perde duvarı örmek.
    for part, layers in (
        ("perde_asansör", ("Asansör",)),
        ("baca", ("C_baca", "HavaBaca")),
    ):
        rs = [r for lyr in layers for r in floor.layer(lyr)]
        if not rs:
            continue
        base = so.union_polygons(so.to_polygons(rs, u))
        shaft = shell_polys(base, cfg.shaft_wall)
        if shaft:
            put(part, so.extrude(shaft, h_wall).translate((0, 0, z_wall)))

    # ------------------------------------------ merdiven (basamak + sahanlık)
    # Merdiven/koridor BOŞLUKtur; duvardan zaten void_layers ile çıkarıldı.
    # Burada sadece C_merdiven basamaklarını çiziyoruz.
    if cfg.stairs:
        treads = floor.layer("C_merdiven")
        if treads:
            acc = None
            for polys, z, th in stair_polys(treads, u, z_wall, h_wall / 2.0):
                m = so.extrude(polys, th).translate((0, 0, z))
                acc = m if acc is None else acc + m
            if acc is not None:
                put("merdiven", acc)

    return out


# ------------------------------------------------------------------ bina
def build_building(
    plan,
    stack: list[tuple[str, int]] | None = None,
    heights_cm: dict[str, float] | None = None,
    cfg: Config | None = None,
    verbose: bool = True,
) -> tuple[dict[str, "object"], dict]:
    """Katları Z ekseninde üst üste yığarak tüm binayı üretir.

    Args:
        plan: ``dxfio.load_plan(..., local_coords=True)`` çıktısı
        stack: ``[(pafta_adı, tekrar), ...]`` (varsayılan ``DEFAULT_STACK``)
        heights_cm: ``{"bodrum_kat": 300, ...}`` kat yükseklikleri (cm)
        cfg: :class:`Config`

    Returns:
        (parça adı -> manifold, istatistik sözlüğü)
    """
    cfg = cfg or Config()
    stack = stack or list(DEFAULT_STACK)
    heights_cm = heights_cm or {}
    u = plan.unit_to_metre

    merged: dict[str, list] = {}
    z = 0.0
    storeys: list[dict] = []

    for key, count in stack:
        if key not in plan.floors:
            print(f"  ! '{key}' paftası yok, atlanıyor")
            continue
        floor = plan.floors[key]
        H = float(heights_cm.get(key, 300.0)) / 100.0
        for i in range(int(count)):
            label = key if count == 1 else f"{key}#{i + 1}"
            parts = build_storey(floor, u, z, H, cfg)
            merged.setdefault("_all", []).extend(parts.items())
            storeys.append({"ad": label, "z0": z, "H": H,
                            "parçalar": {k: v.volume() for k, v in parts.items()}})
            if verbose:
                print(f"  {label:<16} z={z:5.2f}..{z + H:5.2f} m  "
                      f"({len(parts)} parça)")
            for name, man in parts.items():
                merged.setdefault(name, []).append(man)
            z += H

    # son (çatı) döşemesi
    roof_floor_key = stack[-1][0] if stack else None
    if roof_floor_key and roof_floor_key in plan.floors:
        fl = plan.floors[roof_floor_key]
        rp = so.union_polygons(so.to_polygons(
            fl.layer("Bina_kontur") + fl.layer("B_balkon"), u))
        if rp:
            merged.setdefault("döseme", []).append(
                so.extrude(rp, cfg.slab).translate((0, 0, z)))

    # parçaları tek gövdeye indir
    result: dict[str, object] = {}
    stats: list[tuple[str, float]] = []
    for name, mans in merged.items():
        if name == "_all" or not mans:
            continue
        acc = mans[0]
        for m in mans[1:]:
            acc = acc + m
        if acc.is_empty():
            continue
        result[name] = acc
        stats.append((name, acc.volume()))

    info = {
        "kat sayısı": len(storeys),
        "toplam yükseklik": z,
        "katlar": storeys,
        "hacimler": dict(sorted(stats, key=lambda kv: -kv[1])),
    }
    return result, info
