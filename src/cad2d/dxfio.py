"""ezdxf ile DXF okuma, INSERT açma (flatten) ve kat paftası / profil çıkarma.

Bu modül saf 2B'dir: sadece ``(x, y)`` ring listesi üretir.
3B'ye geçiş ``cad2d.solid`` modülünde yapılır.

Tipik kullanım::

    import cad2d.dxfio as dx
    plan = dx.load_plan("data/kavaklik_01.dxf")
    print(plan.summary())
    floor = plan.floors["normal_kat"]
    print(dx.dump_layers(floor.rings, plan.unit_to_metre))
"""
from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Iterator, Sequence

import ezdxf
import numpy as np
from ezdxf.document import Drawing
from ezdxf.entities import DXFEntity
from ezdxf.layouts import Modelspace

# ------------------------------------------------------------------ birimler
# DXF $INSUNITS kodu -> 1 çizim biriminin kaç metre olduğu
INSUNITS_TO_METRE = {
    0: 1.0, 1: 0.0254, 2: 0.3048, 4: 0.001, 5: 0.01, 6: 1.0, 7: 1000.0,
    8: 2.54e-8, 9: 2.54e-5, 10: 0.9144, 11: 1e-10, 12: 1e-9, 13: 1e-6,
    14: 0.1, 15: 10.0, 16: 100.0, 17: 1e9, 18: 149.6e9, 19: 9.461e15,
    20: 3.086e16,
}

UNIT_TO_METRE = {
    "mm": 0.001, "cm": 0.01, "dm": 0.1, "m": 1.0, "inch": 0.0254, "ft": 0.3048,
}

# Büyükten küçüğe ölçek merdiveni (otomatik birim seçimi)
_LADDER = ["m", "cm", "mm"]

# Tipik bir oda ölçüsü (m). Otomatik birim seçiminde hedef değer.
TYPICAL_ROOM_M = 5.0
# Tipik bir bina dış ölçüsü (m). Ölçülendirme yoksa kullanılır.
TYPICAL_BUILDING_M = 60.0


# ------------------------------------------------------------------ veri
@dataclass
class Ring:
    """Tek bir kapalı (veya açık) 2B poligon (WCS, çizim birimi)."""

    xy: np.ndarray          # (N, 2) float64
    layer: str = "0"
    kind: str = "LWPOLYLINE"
    closed: bool = True
    source: str = ""        # geldiği üst blok adı (INSERT açılmışsa), yoksa ""

    @property
    def n(self) -> int:
        return len(self.xy)

    def as_metres(self, unit_to_metre: float) -> np.ndarray:
        return self.xy * unit_to_metre

    def area(self, unit_to_metre: float = 1.0) -> float:
        """İşaretli alan (shoelace), birim kare."""
        p = self.xy
        if len(p) < 3:
            return 0.0
        x, y = p[:, 0], p[:, 1]
        return (float(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1))) / 2.0
                * unit_to_metre ** 2)

    def perimeter(self, unit_to_metre: float = 1.0) -> float:
        p = self.xy
        if len(p) < 2:
            return 0.0
        d = np.diff(np.vstack([p, p[:1]]), axis=0)
        return float(np.hypot(d[:, 0], d[:, 1]).sum()) * unit_to_metre

    def bbox(self) -> tuple[float, float, float, float]:
        p = self.xy
        return (float(p[:, 0].min()), float(p[:, 1].min()),
                float(p[:, 0].max()), float(p[:, 1].max()))

    def centroid(self) -> tuple[float, float]:
        p = self.xy
        return (float(p[:, 0].mean()), float(p[:, 1].mean()))


@dataclass
class Floor:
    """Bir kat paftası.

    ``bbox`` pafta çerçevesinin dünya koordinatlarındaki (WCS) sınırıdır.
    Ring koordinatları **ham WCS** değerlerindedir; isterseniz
    ``to_local()`` ile paftaya göre yerelleştirin.
    """

    name: str
    bbox: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0)
    title: str = ""
    source_block: str = ""
    rings: list[Ring] = field(default_factory=list)

    def layer(self, *names: str) -> list[Ring]:
        wanted = set(names)
        return [r for r in self.rings if r.layer in wanted]

    @property
    def layers(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for r in self.rings:
            out[r.layer] = out.get(r.layer, 0) + 1
        return dict(sorted(out.items(), key=lambda kv: -kv[1]))

    def to_local(self) -> None:
        """Ring koordinatlarını paftanın sol-alt köşesine göre kaydırır (yerinde)."""
        x0, y0 = self.bbox[0], self.bbox[1]
        for r in self.rings:
            r.xy = r.xy - np.array([x0, y0])

    def extent_m(self, unit_to_metre: float) -> tuple[float, float]:
        return ((self.bbox[2] - self.bbox[0]) * unit_to_metre,
                (self.bbox[3] - self.bbox[1]) * unit_to_metre)


@dataclass
class Plan:
    """DXF'in tamamı: birim bilgisi, paftalar ve pafta dışı artık geometri."""

    path: Path
    doc: Drawing
    unit: str
    unit_to_metre: float
    insunits: int
    unit_is_consistent: bool
    unit_reason: str = ""
    all_rings: list[Ring] = field(default_factory=list)
    floors: dict[str, Floor] = field(default_factory=dict)
    stray: list[Ring] = field(default_factory=list)

    def summary(self) -> str:
        lines = [
            f"dosya             : {self.path.name}",
            f"DXF sürümü        : {self.doc.dxfversion} ({self.doc.acad_release})",
            f"$INSUNITS         : {self.insunits}",
            f"seçilen birim     : 1 birim = {self.unit} = {self.unit_to_metre} m",
            f"birim tutarlı mı? : {'evet' if self.unit_is_consistent else 'HAYIR -> düzeltildi'}",
            f"  gerekçe         : {self.unit_reason}",
            f"toplam ring       : {len(self.all_rings)}",
            f"kat paftası       : {len(self.floors)}",
        ]
        for name, f in self.floors.items():
            w, h = f.extent_m(self.unit_to_metre)
            lines.append(
                f"  - {name:<16} {len(f.rings):>5} ring   pafta {w:5.1f} x {h:5.1f} m"
                f"   başlık: {f.title or '(yok)'}")
        if self.stray:
            lines.append(f"pafta dışı artık  : {len(self.stray)} ring")
        return "\n".join(lines)


# ------------------------------------------------------------------ yardımcı
def _poly_points(e: DXFEntity) -> list[tuple[float, float]] | None:
    """LWPOLYLINE / POLYLINE / CIRCLE / ARC / LINE -> [(x, y), ...] (blok yereli)."""
    t = e.dxftype()
    if t == "LWPOLYLINE":
        return [(float(p[0]), float(p[1])) for p in e.get_points("xy")]
    if t == "POLYLINE":
        return [(float(v.dxf.location.x), float(v.dxf.location.y))
                for v in e.vertices()]
    if t == "CIRCLE":
        c, r = e.dxf.center, float(e.dxf.radius)
        n = 32
        return [(c.x + r * math.cos(2 * math.pi * i / n),
                 c.y + r * math.sin(2 * math.pi * i / n)) for i in range(n)]
    if t == "ARC":
        c, r = e.dxf.center, float(e.dxf.radius)
        a0 = math.radians(float(e.dxf.start_angle))
        a1 = math.radians(float(e.dxf.end_angle))
        if a1 < a0:
            a1 += 2 * math.pi
        n = 48
        return [(c.x + r * math.cos(a0 + (a1 - a0) * i / n),
                 c.y + r * math.sin(a0 + (a1 - a0) * i / n)) for i in range(n + 1)]
    if t == "LINE":
        s, en = e.dxf.start, e.dxf.end
        return [(s.x, s.y), (en.x, en.y)]
    return None


def _is_closed(e: DXFEntity, pts: Sequence[tuple[float, float]]) -> bool:
    try:
        return bool(e.closed)
    except (AttributeError, TypeError, ValueError):
        pass
    if len(pts) < 3:
        return False
    return math.hypot(pts[0][0] - pts[-1][0], pts[0][1] - pts[-1][1]) < 1e-9


def as_matrix(m) -> np.ndarray:
    """ezdxf ``Matrix44`` / dizi / None -> (4, 4) float64 satır-vektör matrisi.

    ezdxf satır-vektör kuralını kullanır: ``p' = p @ M``.
    """
    if m is None:
        return np.eye(4)
    if hasattr(m, "get_row"):                 # ezdxf.acc.matrix44.Matrix44
        return np.asarray([m.get_row(i) for i in range(4)], dtype=float)
    return np.asarray(m, dtype=float)


def _apply_matrix(m, pts: Sequence[tuple[float, float]]) -> np.ndarray:
    """(4,4) matrisi satır-vektör kuralıyla uygular; (N, 2) döner."""
    a = np.asarray(pts, dtype=float)
    if a.size == 0:
        return a
    M = as_matrix(m)
    # satır-vektör: (x, y, 0, 1) @ M  -> öteleme M'nin SON SATIRINDADIR
    hom = np.hstack([a, np.zeros((len(a), 1)), np.ones((len(a), 1))])
    return np.ascontiguousarray((hom @ M)[:, :2])


def flatten_inserts(
    entities: Iterable[DXFEntity],
    max_depth: int = 8,
) -> Iterator[tuple[DXFEntity, "np.ndarray | None", str]]:
    """INSERT'leri özyinelemeli açarak ``(entity, world_matrix, üst_blok)`` üretir.

    ``üst_blok`` en dıştaki INSERT'in blok adıdır (iç içe bloklarda da korunur);
    doğrudan modelspace geometrisi için boş string.
    """
    stack: list[tuple[DXFEntity, np.ndarray | None, int, str]] = [
        (e, None, 0, "") for e in entities
    ]
    while stack:
        e, m, depth, src = stack.pop()
        if e.dxftype() == "INSERT" and depth < max_depth:
            try:
                blk = e.block()
            except Exception:  # noqa: BLE001
                blk = None
            if blk is None:
                continue
            try:
                m2 = as_matrix(e.matrix44())
                # satır-vektör kuralı: çocuk-yerel -> ebeveyn-yerel -> dünya
                new_m = m2 if m is None else m2 @ as_matrix(m)
            except Exception:  # noqa: BLE001
                new_m = m
            top = src or str(e.dxf.name)
            for se in blk:
                stack.append((se, new_m, depth + 1, top))
            continue
        yield e, m, src


def _rings_from(entities: Iterable[DXFEntity], max_depth: int = 8) -> list[Ring]:
    out: list[Ring] = []
    for e, m, src in flatten_inserts(entities, max_depth=max_depth):
        pts = _poly_points(e)
        if not pts or len(pts) < 2:
            continue
        xy = _apply_matrix(m, pts)
        out.append(Ring(
            xy=np.ascontiguousarray(xy, dtype=float),
            layer=str(e.dxf.layer),
            kind=e.dxftype(),
            closed=_is_closed(e, pts),
            source=src,
        ))
    return out


# ------------------------------------------------------------------ birim
def median_dimension(doc: Drawing) -> float | None:
    """Modelspace'teki DIMENSION'ların medyan ölçüsü (çizim birimi)."""
    vals: list[float] = []
    for e in doc.modelspace().query("DIMENSION"):
        try:
            v = abs(float(e.get_measurement()))
        except Exception:  # noqa: BLE001
            continue
        if v > 0:
            vals.append(v)
    return float(np.median(vals)) if vals else None


def infer_unit(doc: Drawing, rings: Sequence[Ring]) -> tuple[str, float, bool, str]:
    """Çizim birimini metreye çeviren katsayıyı belirler.

    1. ``$INSUNITS`` haritasından başla (yoksa 'm').
    2. Düzeltme sinyalleri:
       * Ölçülendirme değerlerinin medyanı -> tipik bir oda ölçüsüne (5 m)
         en yakın birimi seç.  (Birçok Türk mimari çiziminde ``$INSUNITS=6``
         yani "metre" yazılıdır ama geometri santimetredir.)
       * Ölçülendirme yoksa bina dış ölçüsünü kullan (hedef 60 m).
    """
    ins = int(doc.header.get("$INSUNITS", 0) or 0)
    start_m = INSUNITS_TO_METRE.get(ins, 1.0)
    inv = {v: k for k, v in UNIT_TO_METRE.items()}
    unit = inv.get(start_m, "m")
    if unit not in _LADDER:
        unit = "m"

    med = median_dimension(doc)
    if med and med > 0:
        target, signal = TYPICAL_ROOM_M, f"medyan ölçülendirme = {med:.0f} birim"
    elif rings:
        bb = np.array([r.bbox() for r in rings if r.n])
        target = TYPICAL_BUILDING_M
        med = float(max((bb[:, 3] - bb[:, 1]).max(),
                        np.median(bb[:, 2] - bb[:, 0])))
        signal = f"tipik ring genişliği = {med:.0f} birim"
    else:
        return unit, UNIT_TO_METRE[unit], True, "$INSUNITS (kontrol edilemedi)"

    best = min(_LADDER, key=lambda u: abs(math.log(UNIT_TO_METRE[u] * med / target)))
    consistent = (best == unit)
    if consistent:
        reason = f"{signal}; $INSUNITS={ins} -> {unit} doğrulandı"
    else:
        reason = (f"{signal}; {unit} ile {med * UNIT_TO_METRE[unit]:.1f} m olurdu "
                  f"(gerçekçi değil) -> {best} seçildi "
                  f"({med * UNIT_TO_METRE[best]:.2f} m)")
    return best, UNIT_TO_METRE[best], consistent, reason


# ------------------------------------------------------------------ paftalar
def _frame_candidates(rings: Sequence[Ring]) -> list[Ring]:
    """Pafta çerçevesi olabilecek ringler: 'pafta' katmanı, 4-5 noktalı dikdörtgen."""
    cand = [r for r in rings if "pafta" in r.layer.lower() and r.n in (4, 5)]
    if not cand:
        return []
    biggest = max(abs(r.area()) for r in cand)
    return [r for r in cand if abs(r.area()) >= 0.5 * biggest]


def _titles(doc: Drawing) -> list[tuple[float, float, str]]:
    out = []
    for e in doc.modelspace().query("MTEXT TEXT"):
        try:
            txt = e.text if e.dxftype() == "TEXT" else e.text
        except Exception:  # noqa: BLE001
            continue
        txt = txt.replace("\\P", " ")
        for tag in ("\\H", "\\W", "\\f", "{"):
            txt = txt.replace(tag, " ")
        txt = " ".join(txt.replace(";", " ").split())
        pos = e.dxf.insert
        out.append((float(pos.x), float(pos.y), txt))
    return out


def _clean_title(txt: str) -> str:
    return " ".join(txt.split())


def detect_floors(doc: Drawing, rings: Sequence[Ring]) -> tuple[dict[str, Floor],
                                                                list[Ring]]:
    """Modelspace'i pafta çerçevelerine göre kat planlarına ayırır.

    Returns:
        (floors, stray) — stray hiçbir paftaya girmeyen ringlerdir.
    """
    cand = _frame_candidates(rings)
    # aynı çerçeveyi tekrar eden ringleri tekilleştir (yuvarlanmış sol-alt köşe)
    frames: dict[tuple[int, int], Ring] = {}
    for r in cand:
        x0, y0, _x1, _y1 = r.bbox()
        key = (round(x0), round(y0))
        prev = frames.get(key)
        if prev is None or abs(r.area()) > abs(prev.area()):
            frames[key] = r

    floors: dict[str, Floor] = {}
    stray: list[Ring] = []
    titles = _titles(doc)

    # her ring'i içine alan (en küçük) çerçeveye ata
    frame_list = sorted(frames.values(),
                        key=lambda r: (r.bbox()[1], r.bbox()[0]))
    boxes = [f.bbox() for f in frame_list]
    assigned: list[list[Ring]] = [[] for _ in frame_list]

    for r in rings:
        cx, cy = r.centroid()
        best_i, best_area = -1, float("inf")
        for i, (x0, y0, x1, y1) in enumerate(boxes):
            if x0 - 1e-6 <= cx <= x1 + 1e-6 and y0 - 1e-6 <= cy <= y1 + 1e-6:
                a = (x1 - x0) * (y1 - y0)
                if a < best_area:
                    best_i, best_area = i, a
        if best_i >= 0:
            assigned[best_i].append(r)
        else:
            stray.append(r)

    used: set[str] = set()
    for i, fr in enumerate(frame_list):
        x0, y0, x1, y1 = boxes[i]
        members = assigned[i]
        # aday ad: çerçevenin kendi geldiği blok (yoksa konuma göre pafta_N)
        srcs = [r.source for r in members if r.source]
        block_name = max(set(srcs), key=srcs.count) if srcs else ""
        name = fr.source or ""
        # başlık: pafta içindeki "PLAN" geçen metin
        title = ""
        for tx, ty, txt in titles:
            if x0 <= tx <= x1 and y0 <= ty <= y1 and "PLAN" in txt.upper():
                title = _clean_title(txt)
                break
        if not name:
            name = "pafta_%d" % (i + 1)
        if name in used:
            k = 2
            while f"{name}#{k}" in used:
                k += 1
            name = f"{name}#{k}"
        used.add(name)
        floors[name] = Floor(name=name, bbox=(x0, y0, x1, y1), title=title,
                             source_block=block_name, rings=members)
    return floors, stray


def load_plan(
    path: str | Path,
    unit: str | None = None,
    max_depth: int = 8,
    local_coords: bool = False,
) -> Plan:
    """DXF'i oku, INSERT'leri aç, kat paftalarını ayır, birimi belirle."""
    p = Path(path)
    doc = ezdxf.readfile(p)
    msp: Modelspace = doc.modelspace()

    rings = _rings_from(msp, max_depth=max_depth)

    if unit is not None:
        u = unit.lower()
        if u not in UNIT_TO_METRE:
            raise ValueError(f"bilinmeyen birim: {unit!r}; {sorted(UNIT_TO_METRE)}")
        unit_name, factor, consistent, reason = u, UNIT_TO_METRE[u], True, \
            f"kullanıcı --unit {u}"
    else:
        unit_name, factor, consistent, reason = infer_unit(doc, rings)

    floors, stray = detect_floors(doc, rings)
    if local_coords:
        for f in floors.values():
            f.to_local()

    return Plan(path=p, doc=doc, unit=unit_name, unit_to_metre=factor,
                insunits=int(doc.header.get("$INSUNITS", 0) or 0),
                unit_is_consistent=consistent, unit_reason=reason,
                all_rings=rings, floors=floors, stray=stray)


def dump_layers(rings: Sequence[Ring], unit_to_metre: float = 0.01) -> str:
    """Katman envanterini insan-okur tabloya döker."""
    per: dict[str, list[Ring]] = defaultdict(list)
    for r in rings:
        per[r.layer].append(r)
    head = (f"{'katman':<16}{'ring':>6}{'kapalı':>8}{'nokta':>8}"
            f"{'alan top m²':>14}{'alan min':>11}{'alan max':>11}")
    lines = [head, "-" * len(head)]
    for layer in sorted(per, key=lambda l: -len(per[l])):
        rs = per[layer]
        closed = [r for r in rs if r.closed and r.n >= 3]
        areas = [abs(r.area(unit_to_metre)) for r in closed]
        lines.append(
            f"{layer:<16}{len(rs):>6}{len(closed):>8}{sum(r.n for r in rs):>8}"
            f"{sum(areas):>14.2f}"
            f"{(min(areas) if areas else 0.0):>11.3f}"
            f"{(max(areas) if areas else 0.0):>11.3f}")
    return "\n".join(lines)
