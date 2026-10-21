"""cad2d — 2B DXF mimari planlardan 3B katı model üretim hattı.

Katmanlar:
    cad2d.dxfio   -> ezdxf ile okuma, INSERT açma (flatten), katman/profil çıkarma
    cad2d.solid   -> shapely temizliği + manifold3d ile extrude/CSG
    cad2d.view    -> trimesh ile sahne kurma, GLB/OBJ dışa aktarma, HTML izleyici

Tipik akış:
    plan = cad2d.dxfio.load_plan("data/kavaklik_01.dxf")
    floor = plan.floors["normal_kat"]
    solid = cad2d.solid.slab(floor.layer("C_kolon"), z0=0.0, height=300.0)
    mesh  = cad2d.solid.to_trimesh(solid, color=(0.8, 0.3, 0.2))
"""

from __future__ import annotations

__version__ = "0.1.0"

__all__ = ["dxfio", "solid", "view"]
