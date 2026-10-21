# Nasıl Kullanacağım? — Adım Adım

Bu depo şu an github.com/mustafa84021/cad2d → `arena/d32255e4-cad2d` dalında.
Aşağıdaki adımlar **sıfırdan** kurulum içindir.

---

## 1. Kodu bilgisayarına al

Daha önce klonlamadıysan:

```bash
git clone https://github.com/mustafa84021/cad2d.git
cd cad2d
git checkout arena/d32255e4-cad2d
```

Zaten klonladıysan:

```bash
cd cad2d
git fetch origin
git checkout arena/d32255e4-cad2d
git pull
```

Son hali görmek için: `git log --oneline -1` → `b4c6323 ezdxf+manifold3d+trimesh hatti...`

---

## 2. ⚠️ DXF dosyasını `data/` klasörüne koy

**Önemli:** `data/` ve `out/` klasörleri `.gitignore`'da — yani `kavaklik_01.dxf`
**repo'ya commit edilmedi** (1.2 MB'lık kullanıcı verisi). Kendi DXF'ini kendin
koymalısın:

```
cad2d/
├── data/                 ← DXF'lerini buraya at (git'e girmez)
│   └── kavaklik_01.dxf
├── out/                  ← çıktılar buraya yazılır (otomatik oluşur, git'e girmez)
├── src/cad2d/
├── scripts/
└── docs/
```

Google Drive'dan indirdiysen doğrudan `data/` içine sürükle; alt klasör de
olur, `--dxf` ile yolu verirsin.

---

## 3. Sanal ortam + bağımlılıklar

### 🚀 Tek komut (önerilen)

`setup.sh` / `setup.ps1` her şeyi yapar: `.venv` kurar, bağımlılıkları yükler,
`data/` + `out/` klasörlerini açar ve `data/` içindeki DXF'in pafta listesini
yazdırır.

```bash
# macOS / Linux / WSL / Git Bash
./setup.sh
```

```powershell
# Windows PowerShell
.\setup.ps1
```

Elle kurmak istersen aşağıdaki adımları izle (aynı işi yapar).

### Windows (PowerShell)

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

> `Activate.ps1` "bu betiğe izin yok" derse, yönetici olarak bir kez:
> `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`

### macOS / Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

Test edilen sürümler:

| Paket | Sürüm |
|---|---|
| Python | 3.11 |
| ezdxf | 1.4.5 |
| numpy | 2.4.6 |
| shapely | 2.2.0 |
| manifold3d | 3.5.4 |
| trimesh | 5.1.1 |
| matplotlib | 3.11.2 |

Kurulum doğrulama:

```bash
python -c "import ezdxf, shapely, manifold3d, trimesh; print('tamam')"
```

---

## 4. VS Code'da aç

```bash
code .
```

Açıldığında VS Code sağ altta **"Select Interpreter"** isteyebilir →
`./.venv/bin/python` (Windows: `.venv\Scripts\python.exe`) seç.
Gelmezse `Ctrl/Cmd+Shift+P` → `Python: Select Interpreter`.

`.vscode/` klasörü hazır geliyor:

| Dosya | Ne sağlıyor |
|---|---|
| `settings.json` | interpreter yolu, `PYTHONPATH=src` (→ `import cad2d` çalışır), format-on-save |
| `launch.json` | **4 hazır debug config** — `F5`'e bas, listeden seç |
| `tasks.json` | `Ctrl/Cmd+Shift+B` → `DXF analiz` / `2B plan önizleme` / `3B model üret` |
| `extensions.json` | Python, Pylance, Black, Ruff önerileri |

**En hızlı yol:** `F5` → **"2B -> 3B model üret (build3d.py)"** → çalışır, `out/`
dolusu çıktı üretir.

---

## 5. Dört temel komut

Aşağıdakiler proje kökünde, venv aktifken çalışır.

### 5.1 Ne var? (her yeni DXF'te ilk bunu çalıştır)

```bash
# Windows
python scripts\build3d.py --list
# macOS/Linux
python scripts/build3d.py --list
```

Çıktısı birim tespitini, pafta adlarını ve bina ölçülerini verir:

```
seçilen birim     : 1 birim = cm = 0.01 m
birim tutarlı mı? : HAYIR -> düzeltildi
kat paftası       : 6
  - bodrum_kat   193 ring   başlık: BODRUM KAT PLANI Ö:1/50
  - zemin_kat    264 ring   başlık: ZEMİN KAT PLANI Ö:1/50
  - normal_kat   859 ring   başlık: NORMAL KAT PLANI Ö:1/50
  - pafta_4      100 ring   başlık: (yok)
  - pafta_5      106 ring
  - pafta_6      813 ring
```

**Buradaki pafta adını kopyala**, bir sonraki adımda `--floor` ile ver.

### 5.2 Bir katı 3B'ye çevir

```bash
python scripts/build3d.py --floor normal_kat --openings --out out/normal_kat.glb
```

Üretir:
- `out/normal_kat.glb` — 3B model
- `out/normal_kat.html` — **tarayıcıda açılan** etkileşimli izleyici

`out/normal_kat.html` dosyasına **çift tıkla**; three.js CDN'den yüklenir
(internet gerekir). Fare sol tuş döndür, tekerlek yakınlaş, `W` tel-kafes,
`F` çerçevele, `1/2/3` eksen görünümleri.

### 5.3 Tüm paftalar

```bash
python scripts/build3d.py --all --openings --out out/model.glb
```

`out/index.html` üretir — 6 paftanın kart listesi. Karta tıkla, 3B açılır.
(Canlı önizlemede şu an bunun aynısı çalışıyor.)

### 5.4 2B plan görüntüsü (PNG)

```bash
# tüm çizim
python scripts/preview_dxf.py data/kavaklik_01.dxf -o out/preview.png

# sadece normal_kat paftası (yakınlaştırma)
python scripts/preview_dxf.py data/kavaklik_01.dxf \
       --bbox 12600,6000,18900,12000 -o out/plan_normal_kat.png

# sadece kolon + duvar konturu
python scripts/preview_dxf.py data/kavaklik_01.dxf --layers C_kolon,Bina_kontur \
       -o out/kolonlar.png
```

---

## 6. Parametreler — neyi değiştiririm?

Hepsi `build3d.py` içinde, **hepsi cm cinsinden**:

| Parametre | Varsayılan | Ne yapar |
|---|---|---|
| `--wall-height` | `300` | Kat yüksekliği (300 cm = 3.0 m) |
| `--slab` | `20` | Döşeme kalınlığı |
| `--sill` | `90` | Pencere denizlik yüksekliği |
| `--window-height` | `150` | Pencere yüksekliği |
| `--door-height` | `210` | Kapı yüksekliği |
| `--openings` | kapalı | **Aç:** pencere/kapı boşluklarını duvardan CSG ile çıkar |
| `--unit` | otomatik | Birimi zorla: `--unit cm` / `mm` / `m` |
| `--local` | kapalı | Koordinatları pafta sol-altına taşı (modeli orijine yaklaştırır) |
| `--min-wall-area` | `0.05` | Bu alanın altındaki duvar kırpıntılarını at (m²) |
| `--obj` | kapalı | Ayrıca `.obj` yaz |

Örnek — 3.2 m kat, 25 cm döşeme, boşluklar açık:

```bash
python scripts/build3d.py --floor normal_kat --openings --local \
       --wall-height 320 --slab 25 --out out/normal_kat.glb
```

---

## 7. Kendi DXF'imle nasıl kullanırım?

```bash
# 1) koy
cp ~/Downloads/projem.dxf data/

# 2) ne var bak  (pafta adlarını ve birimi öğren)
python scripts/build3d.py --dxf data/projem.dxf --list

# 3) üret
python scripts/build3d.py --dxf data/projem.dxf --floor <pafta_adı> \
       --openings --out out/projem.glb
```

**Birim yanlış çıkarsa** (bina 100 kat büyük/küçük görünürse) `--unit` ile zorla:

```bash
python scripts/build3d.py --dxf data/projem.dxf --unit mm --list
```

Pafta adı `--list`'te görünmüyorsa (ör. çizim tek parça, `C_pafta` katmanı yok),
bütün çizim tek pafta sayılır → `--floor` vermeden çalıştır.

---

## 8. Notebook / kendi kodunda kullanım

```python
# proje kökünde bir deneme.ipynb aç (PYTHONPATH=src .vscode'dan gelir)
import cad2d.dxfio as dx, cad2d.solid as so, cad2d.view as vw

plan = dx.load_plan("data/kavaklik_01.dxf")
print(plan.summary())

floor = plan.floors["normal_kat"]
u = plan.unit_to_metre                      # 0.01 (cm)

# odaları tek tek dolaş, alanlarını yazdır
for r in floor.layer("C_oda"):
    print(f"{r.layer:8s} {abs(r.area(u)):8.2f} m²  {r.n} nokta")

# kolonları 3 m extrude et
cols = so.extrude(so.union_polygons(so.to_polygons(floor.layer("C_kolon"), u)), 3.0)
mesh = so.to_trimesh(cols, color=(0.76, 0.30, 0.24), name="kolon")

# balkon hacmi
print("balkon hacmi:", so.extrude(
    so.union_polygons(so.to_polygons(floor.layer("B_balkon"), u)), 0.2).volume(), "m³")

vw.export_glb(vw.scene({"kolon": mesh}), "out/sadece_kolonlar.glb")
```

Faydalı fonksiyonlar:

| Fonksiyon | Ne |
|---|---|
| `dx.load_plan(yol, unit=..., local_coords=True)` | oku + paftalara ayır |
| `dx.dump_layers(floor.rings, u)` | katman envanteri tablosu |
| `floor.layer("C_kolon")` | katmana göre ring listesi |
| `so.to_polygons(rings, u)` | shapely poligonu (metre) |
| `so.union_polygons(polys)` | birleştir |
| `so.extrude(polys, yükseklik)` | manifold3d katı |
| `so.walls_from_contour(kontur, boşluklar, z0, h, u)` | duvar türet |
| `so.boolean(a, b, "subtract")` | CSG (`add` / `subtract` / `intersect`) |
| `so.to_trimesh(m, color=...)` | manifold → trimesh |
| `vw.export_glb(scene, yol)` / `vw.write_html_viewer(glb, html)` | çıktı |

---

## 9. Sık karşılaşılan sorunlar

**`ModuleNotFoundError: No module named 'cad2d'`**
VS Code interpreter'ı `.venv` değil. `Ctrl/Cmd+Shift+P` → `Python: Select Interpreter`.
Notebook/script'i proje kökünden çalıştır. Gerekirse script başına
`sys.path.insert(0, "src")` ekle.

**`trimesh.SceneViewer` açılmıyor / `pyglet` hatası**
Etkileşimli trimesh penceresi gerçek ekran ister; headless/uzak ortamda çalışmaz.
`vw.show(scene)` yerine `vw.export_glb(...)` + `vw.write_html_viewer(...)` kullan
(HTML'i tarayıcıda aç).

**3B model boş / hiç gövde yok**
Konsolda `! duvar: boş gövde` yazıyorsa iç mekân poligonları konturu tamamen
kaplıyordur. `--min-wall-area 0.01` ile küçült veya ilgili katmanı `VOID_LAYERS`
listesinden çıkar (`scripts/build3d.py`).

**Bina 100 kat büyük/küçük**
Birim tespiti yanlış. `--unit cm` / `--unit mm` ile zorla. Detay:
`docs/ANALIZ_kavaklik_01.md` §1.

**HTML açılıyor ama model görünmüyor**
`three.js` CDN'den (`unpkg.com`) yükleniyor — internet bağlantısı gerekir.
Ayrıca `.glb` ve `.html` dosyaları **aynı klasörde** durmalı.

**Pafta adları `pafta_4` gibi çıkıyor**
Çizimde o paftanın başlık yazısı yok. `scripts/build3d.py` içindeki
`detect_floors()` adını pafta içindeki metinden alır.

---

## 10. Dosya haritası

| Yol | Ne zaman açarsın |
|---|---|
| `README.md` | genel bakış, komut özeti |
| `docs/KULLANIM.md` | **bu dosya** — kurulum ve kullanım |
| `docs/ANALIZ_kavaklik_01.md` | örnek DXF'in tam envanteri, ölçüler, eksikler |
| `src/cad2d/dxfio.py` | birim/pafta tespiti mantığı |
| `src/cad2d/solid.py` | shapely + manifold3d (duvar türetme, CSG) |
| `src/cad2d/view.py` | trimesh → GLB + three.js HTML |
| `scripts/build3d.py` | ana çalıştırılabilir; `VOID_LAYERS` ve `PARTS` burada |
| `scripts/preview_dxf.py` | 2B PNG; `STYLE` sözlüğünde katman renkleri |
