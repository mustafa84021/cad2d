"""2B ring -> 3B katı model: shapely temizliği + manifold3d CSG + trimesh mesh.

manifold3d ``CrossSection`` bireyler-arası kesişmeyen poligonlar ister; bu
yüzden ringler önce shapely ile temizlenir (``buffer(0)``) ve birleştirilir.
"""
from __future__ import annotations

from typing import Iterable, Sequence

import manifold3d as m3d
import numpy as np
import shapely
import trimesh
from shapely.geometry import Polygon
from shapely.ops import unary_union

from .dxfio import Ring

__all__ = [
    "to_polygons",
    "union_polygons",
    "cross_section",
    "extrude",
    "box",
    "boolean",
    "to_trimesh",
    "slab",
    "walls_from_contour",
]


# ------------------------------------------------------------------ 2B hazırlık
def _ring_polygon(r: Ring, tol: float = 1e-6) -> Polygon | None:
    if r.n < 3:
        return None
    p = r.xy.astype(float)
    try:
        poly = Polygon(p)
    except Exception:  # noqa: BLE001
        return None
    if poly.is_empty:
        return None
    if not poly.is_valid:
        poly = shapely.make_valid(poly)
    if poly.is_empty or poly.geom_type == "GeometryCollection":
        # make_valid çoklu geometri dönebilir; en büyük poligonu al
        polys = [g for g in getattr(poly, "geoms", []) if g.geom_type == "Polygon"]
        if not polys:
            return None
        poly = max(polys, key=lambda g: g.area)
    if poly.geom_type != "Polygon":
        return None
    if poly.area < tol:
        return None
    return poly


def to_polygons(
    rings: Sequence[Ring] | Iterable[Ring],
    unit_to_metre: float = 0.01,
    repair: bool = True,
    min_area: float = 1e-6,
) -> list[Polygon]:
    """Ring listesini temiz shapely poligonlarına çevirir (metre cinsinden)."""
    out: list[Polygon] = []
    for r in rings:
        if not r.closed:
            # açık polyline: kapatılabilir mi?
            if r.n < 3:
                continue
        poly = _ring_polygon(r)
        if poly is None:
            continue
        if unit_to_metre != 1.0:
            poly = shapely.affinity.scale(
                poly, unit_to_metre, unit_to_metre, origin=(0, 0))
        if repair and not poly.is_valid:
            poly = poly.buffer(0)
        if poly.is_empty or poly.area < min_area:
            continue
        out.append(poly)
    return out


def union_polygons(polys: Sequence[Polygon]) -> list[Polygon]:
    """Poligonları birleştir; sonucu tekil Polygon listesine indirger."""
    if not polys:
        return []
    g = unary_union(list(polys))
    return _flatten_polygons(g)


def _flatten_polygons(g) -> list[Polygon]:
    if g.is_empty:
        return []
    if g.geom_type == "Polygon":
        return [g]
    out: list[Polygon] = []
    for sub in getattr(g, "geoms", []):
        if sub.geom_type == "Polygon":
            out.append(sub)
        elif sub.geom_type == "MultiPolygon":
            out.extend(sub.geoms)
    return out


def _signed_area(ring: np.ndarray) -> float:
    x, y = ring[:, 0], ring[:, 1]
    return float(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1))) / 2.0


def _contours(polys: Sequence[Polygon]) -> list[np.ndarray]:
    """shapely Polygon -> manifold3d CrossSection konturları (dış + iç halkalar).

    manifold3d ``FillRule.Positive`` bekler: dış halka POZİTİF (CCW),
    delikler NEGATİF (CW) yönlü olmalı.  shapely'nin ``difference`` çıktısı
    bunun tersidir (dış CW, delik CCW), bu yüzden yönleri burada düzeltiyoruz.
    """
    contours: list[np.ndarray] = []
    for p in polys:
        shell = np.asarray(p.exterior.coords, dtype=float)[:-1]
        if len(shell) >= 3:
            if _signed_area(shell) < 0:
                shell = shell[::-1]
            contours.append(np.ascontiguousarray(shell))
        for hole in p.interiors:
            h = np.asarray(hole.coords, dtype=float)[:-1]
            if len(h) < 3:
                continue
            if _signed_area(h) > 0:
                h = h[::-1]
            contours.append(np.ascontiguousarray(h))
    return contours


# ------------------------------------------------------------------ CSG
def cross_section(polys: Sequence[Polygon]) -> m3d.CrossSection:
    if not polys:
        raise ValueError("boş poligon listesi")
    return m3d.CrossSection(_contours(polys), m3d.FillRule.Positive)


def extrude(
    polys: Sequence[Polygon],
    height: float,
    n_divisions: int = 0,
    twist_degrees: float = 0.0,
) -> m3d.Manifold:
    """Poligonları Z boyunca extrude eder (metre cinsinden yükseklik)."""
    return m3d.Manifold.extrude(cross_section(polys), float(height),
                                n_divisions, float(twist_degrees))


def box(size: Sequence[float], center: Sequence[float] | None = None) -> m3d.Manifold:
    """Eksen hizalı kutu."""
    sx, sy, sz = (float(v) for v in size)
    m = m3d.Manifold.cube((sx, sy, sz), center=True)
    if center is not None:
        cx, cy, cz = (float(v) for v in center)
        m = m.translate((cx, cy, cz))
    return m


def boolean(a: m3d.Manifold, b: m3d.Manifold, op: str = "subtract") -> m3d.Manifold:
    """``op``: 'add' (union) | 'subtract' (difference) | 'intersect'."""
    op = op.lower()
    if op in ("add", "union", "+"):
        return a + b
    if op in ("subtract", "difference", "-"):
        return a - b
    if op in ("intersect", "&"):
        return a ^ b
    raise ValueError(f"bilinmeyen op: {op!r}")


def status_ok(m: m3d.Manifold) -> bool:
    """Manifold geçerli mi? (Manifold.status() bir Error enum döner.)"""
    return m.status() == m3d.Error.NoError


# ------------------------------------------------------------------ trimesh
def to_trimesh(m: m3d.Manifold, color: Sequence[float] = (0.75, 0.75, 0.78),
               name: str = "solid") -> trimesh.Trimesh:
    """manifold3d -> trimesh.Trimesh (vertex renkleriyle)."""
    mesh = m.to_mesh()
    verts = np.asarray(mesh.vert_properties, dtype=float)
    faces = np.asarray(mesh.tri_verts, dtype=np.int64).reshape(-1, 3)
    if verts.shape[1] > 3:
        verts = verts[:, :3]
    # process=True farklı gövdelerin çakışan köşelerini birleştirip non-manifold
    # kenar üretir (özellikle 2 cm sıva kabuğu gibi ince/çok parçalı
    # geometride).  manifold3d çıktısı zaten doğru yönlüdür -> process=False.
    t = trimesh.Trimesh(vertices=verts, faces=faces, process=False)
    rgba = np.tile([*color, 1.0], (len(t.vertices), 1))
    t.visual = trimesh.visual.ColorVisuals(mesh=t, vertex_colors=rgba)
    t.metadata["name"] = name
    return t


# ------------------------------------------------------------------ hazır kalıplar
def slab(rings: Sequence[Ring], z0: float, height: float,
         unit_to_metre: float = 0.01, **kw) -> m3d.Manifold:
    """Bir katmanın ringlerini tek gövde olarak extrude eder ve z0'a taşır."""
    polys = union_polygons(to_polygons(rings, unit_to_metre))
    if not polys:
        raise ValueError("extrude edilecek geçerli poligon yok")
    m = extrude(polys, height, **kw)
    if z0:
        m = m.translate((0.0, 0.0, float(z0)))
    return m


def wall_polys(
    contour: Sequence[Ring],
    voids: Sequence[Ring],
    unit_to_metre: float = 0.01,
    min_wall_area: float = 0.05,
) -> list[Polygon]:
    """Dış konturdan iç boşlukları çıkarıp **sıvalı** duvar poligonlarını verir.

    Planlarda oda poligonları net (sıvalı) yüzeye çizildiği için
    ``kontur − iç mekânlar`` farkı **sıva dahil** duvarı verir.
    """
    outer = union_polygons(to_polygons(contour, unit_to_metre))
    if not outer:
        raise ValueError("dış kontur bulunamadı")
    holes = union_polygons(to_polygons(voids, unit_to_metre))
    if holes:
        walls = _flatten_polygons(
            unary_union(outer).difference(unary_union(holes)))
    else:
        walls = outer
    walls = [p for p in walls if not p.is_empty and p.area >= min_wall_area]
    if not walls:
        raise ValueError("duvar poligonu kalmadı (iç boşluklar konturu tamamen kaplıyor)")
    return walls


def walls_from_contour(
    contour: Sequence[Ring],
    voids: Sequence[Ring],
    z0: float,
    height: float,
    unit_to_metre: float = 0.01,
    min_wall_area: float = 0.05,
) -> tuple[m3d.Manifold, list[Polygon]]:
    """Dış konturdan iç boşlukları çıkararak **sıvalı** duvar gövdesi üretir.

    Args:
        contour: bina dış konturu (``Bina_kontur``)
        voids:   iç mekânlar (odalar, merdiven, koridor, şaftlar...)
        min_wall_area: bu alanın altındaki duvar parçaları atılır (m²)

    Returns:
        (manifold, kullanılan sıvalı duvar poligonları)
    """
    walls = wall_polys(contour, voids, unit_to_metre, min_wall_area)
    m = extrude(walls, height)
    if z0:
        m = m.translate((0.0, 0.0, float(z0)))
    return m, walls
