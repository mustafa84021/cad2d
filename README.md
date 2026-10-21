# cad2d — 2B DXF → 3B katı model

Türk mimari kat planlarını (DXF) okuyup **manifold3d** ile katı gövdeye,
**trimesh** ile görselleştirmeye çeviren çalışma alanı. VS Code ile
kullanılmak üzere kurulmuştur.

```
ezdxf  ──►  shapely  ──►  manifold3d  ──►  trimesh  ──►  .glb + three.js
 DXF       temizlik       extrude/CSG      sahne          tarayıcı
 okuma     boolean        (katı model)     birleştirme    (HTML izleyici)
```

## 📖 Nasıl kullanacağım?

**Adım adım kurulum ve kullanım → [`docs/KULLANIM.md`](docs/KULLANIM.md)**

> ⚠️ `data/` ve `out/` klasörleri `.gitignore`'da: DXF dosyaları repo'ya
> girmez, kendin `data/` içine koyarsın.

Özet:

```bash
git checkout arena/d32255e4-cad2d && git pull
python3 -m venv .venv && ./.venv/bin/pip install -r requirements.txt   # Windows: .\.venv\Scripts\pip
cp kavaklik_01.dxf data/                # DXF'i koy
./.venv/bin/python scripts/build3d.py --list          # paftaları gör
./.venv/bin/python scripts/build3d.py --floor normal_kat --openings --out out/normal_kat.glb
# -> out/normal_kat.html dosyasını tarayıcıda aç
```

## Kurulum (VS Code)

```bash
python3 -m venv .venv
./.venv/bin/pip install -r requirements.txt
```

VS Code'da `Ctrl/Cmd+Shift+P` → **Python: Select Interpreter** → `./.venv/bin/python`.
`.vscode/settings.json` `PYTHONPATH=src` ayarını ve 4 hazır **Run and Debug**
konfigürasyonunu (`DXF analiz`, `2B plan önizleme`, `2B -> 3B model üret`)
otomatik getirir.

> `trimesh.SceneViewer` gerçek bir ekran (X11/Wayland) ister. Headless/VS Code
> içinde `scene.show()` yerine `export_glb()` + `write_html_viewer()` kullanın.

## Hızlı başlangıç

```bash
# 1) pafta envanteri + birim tespiti
./.venv/bin/python scripts/build3d.py --list

# 2) bir katı 3B'ye çevir (GLB + three.js HTML)
./.venv/bin/python scripts/build3d.py --floor normal_kat --openings \
    --wall-height 300 --slab 20 --out out/normal_kat.glb

# 3) tüm paftalar + index.html
./.venv/bin/python scripts/build3d.py --all --openings --out out/model.glb

# 4) 2B plan önizlemesi (PNG)
./.venv/bin/python scripts/preview_dxf.py data/kavaklik_01.dxf -o out/preview.png
./.venv/bin/python scripts/preview_dxf.py data/kavaklik_01.dxf \
    --bbox 12600,6000,18900,12000 -o out/plan_normal_kat.png
```

`out/index.html` bir statik sunucu ile açıldığında her pafta için etkileşimli
3B model sunar.

## Paket yapısı

| Dosya | İş |
|---|---|
| `src/cad2d/dxfio.py` | DXF okuma, INSERT açma (flatten), **birim çıkarımı**, pafta ayırma |
| `src/cad2d/solid.py` | shapely temizliği + `manifold3d` extrude/CSG → `trimesh` |
| `src/cad2d/view.py` | trimesh sahnesi, GLB/OBJ dışa aktarma, three.js HTML izleyici |
| `scripts/audit_dxf.py` | hızlı yapısal denetim (sürüm, katman, blok, sınır) |
| `scripts/analyze_deep.py` | iç içe blok analizi, alan istatistikleri, oda etiketleri |
| `scripts/preview_dxf.py` | matplotlib ile katman renkli 2B plan PNG |
| `scripts/build3d.py` | **uçtan uca** 2B → 3B → GLB + HTML |

## Kütüphane kullanımı

```python
import sys; sys.path.insert(0, "src")
import cad2d.dxfio as dx, cad2d.solid as so, cad2d.view as vw

plan = dx.load_plan("data/kavaklik_01.dxf")     # birim otomatik
print(plan.summary())

floor = plan.floors["normal_kat"]
u = plan.unit_to_metre

walls, polys = so.walls_from_contour(           # kontur − iç mekânlar
    floor.layer("Bina_kontur"),
    [r for l in ("C_oda", "Merdiven", "Merd+Koridor") for r in floor.layer(l)],
    z0=0.0, height=3.0, unit_to_metre=u)

cols = so.extrude(so.union_polygons(so.to_polygons(floor.layer("C_kolon"), u)), 3.0)

sc = vw.scene({"duvar": so.to_trimesh(walls, (0.86, 0.85, 0.80)),
               "kolon": so.to_trimesh(cols,  (0.76, 0.30, 0.24))})
vw.export_glb(sc, "out/model.glb")
vw.write_html_viewer("out/model.glb", "out/model.html")
```

## İki önemli tuzak (bu depoda çözüldü)

1. **ezdxf `Matrix44` satır-vektör kuralı** — `p' = p @ M`, öteleme **son satırda**
   (`M[3,:3]`). `np.asarray(Matrix44)` çalışmaz (`M.get_row(i)` gerekir) ve
   iç içe INSERT'lerde zincir `M_iç @ M_dış` sırasıyla kurulmalıdır.

2. **shapely ↔ manifold3d yön uyumsuzluğu** — `shapely.difference()` dış halkayı
   saat yönünde (negatif alan) verir; `manifold3d.CrossSection(FillRule.Positive)`
   tersini bekler. Düzeltilmezse delikli poligonlar **sessizce boş gövde**
   (`Error.InvalidConstruction`) üretir.

Ayrıca: Türk mimari DXF'lerinde `$INSUNITS = 6` (metre) yazılı olsa da geometri
çoğunlukla **santimetredir**. `dxfio.infer_unit()` ölçülendirme medyanını
kullanarak bunu otomatik düzeltir; emin değilseniz `--unit cm` verin.

## Analiz raporu

`docs/ANALIZ_kavaklik_01.md` — örnek dosyanın tam envanteri (6 pafta, katman
anlamları, kolon/kapı/pencere ölçüleri, oda alanları, eksikler).
