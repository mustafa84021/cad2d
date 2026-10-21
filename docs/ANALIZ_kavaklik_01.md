# `kavaklik_01.dxf` — Yapısal Analiz Raporu

> Üretim: `scripts/audit_dxf.py`, `scripts/analyze_deep.py`, `src/cad2d/dxfio.py`
> Tarih: 2026-10-21 · Depo: `mustafa84021/cad2d`

---

## 0. Özet (TL;DR)

| | |
|---|---|
| **Ne** | Bir apartman/blok binasına ait **6 adet kat planı paftası** |
| **DXF sürümü** | AC1021 — AutoCAD **R2007** |
| **Dosya** | 1.190 KB, 152.876 satır, kaydeden: *Reyfur* |
| **⚠️ Birim** | `$INSUNITS = 6` (**metre**) yazıyor ama **geometri santimetre** → **1 birim = 0.01 m** |
| **Bina oturumu** | ≈ **19.1 × 35.1 m** (yeni revizyonda 19.8 × 33.1 m) |
| **Katlar** | Bodrum / Zemin / Normal — **iki ayrı revizyon** (üst sıra etiketli, alt sıra etiketsiz) |
| **Kritik bulgu** | **Duvar katmanı YOK.** Duvarlar `Bina_kontur − iç mekânlar` farkından türetilmeli |
| **Hazır mı?** | 3B'ye çevrilebilir — hat `src/cad2d/` altında çalışır durumda |

---

## 1. Birim tuzağı (en önemli bulgu)

```
$INSUNITS = 6   →  ezdxf'e göre 1 birim = 1 metre
$MEASUREMENT = 1 (metrik),  $DIMSCALE = 1.0,  $DIMLFAC = 1.0
```

**Bu yanlış.** Beş bağımsız kanıt:

| Kanıt | Çizim birimi | metre okunursa | cm okunursa |
|---|---|---|---|
| Kapı bloğu `kp_90` genişliği | 97 | 97 m ❌ | **0.90 m kapı** ✅ |
| Kapı bloğu `kp_100` genişliği | 105 | 105 m ❌ | **1.00 m kapı** ✅ |
| Kolon kesiti | 30 × 70 | 30 m ❌ | **30 × 70 cm** ✅ |
| Duvar/pencere kalınlığı | 20 | 20 m ❌ | **20 cm duvar** ✅ |
| Asansör kuyusu | 2.24² | 224 m ❌ | **2.24 × 2.24 m** ✅ (etiket: 4.64 m²) |
| En büyük oda | 1868 × 1475 | 1.9 km ❌ | **18.68 × 14.75 m = 275 m²** ✅ (etiket: SIĞINAK 253.45 m²) |

`src/cad2d/dxfio.py` bunu otomatik yakalar: `$INSUNITS`'ten başlar, **ölçülendirme
medyanını** (burada 250 birim) tipik bir oda ölçüsüyle (≈5 m) karşılaştırıp
birimi m → cm → mm merdiveninde kaydırır:

```
seçilen birim     : 1 birim = cm = 0.01 m
birim tutarlı mı? : HAYIR -> düzeltildi
gerekçe           : medyan ölçülendirme = 250 birim; m ile 250.0 m olurdu
                    (gerçekçi değil) -> cm seçildi (2.50 m)
```

> **Dikkat:** Bu dosyayı `ezdxf`/`trimesh` ile açıp `$INSUNITS`'e güvenen her
> araç binayı **100 kat büyük** gösterecektir.

---

## 2. Pafta düzeni — 6 kat planı, 2 sıra

Modelspace 18.9 m × 16.7 m'lik bir alana **3'erli iki sıra** pafta yerleştirilmiş.
Her pafta çerçevesi (`C_pafta`) 6300 × 6000 birim = 63 × 60 m.

```
 Y
 ▲  18000 ┌──────────┬──────────┬──────────┐
 │        │ pafta_4  │ pafta_5  │ pafta_6  │  ← ALT SIRA (revizyon B)
 │        │  100 r   │  106 r   │  813 r   │     başlıksız, ölçülendirmesiz
 │  12000 ├──────────┼──────────┼──────────┤
 │        │bodrum_kat│zemin_kat │normal_kat│  ← ÜST SIRA (revizyon A)
 │        │  193 r   │  264 r   │  859 r   │     başlıklı + ölçülendirmeli
 │   6000 └──────────┴──────────┴──────────┘
 └─────────0───────6300──────12600──────18900──► X
```

| Pafta | Kaynak | Ring | Başlık | Bina konturü | Not |
|---|---|---|---|---|---|
| `bodrum_kat` | blok INSERT | 193 | BODRUM KAT PLANI Ö:1/50 | 19.08 × 35.05 m (558.3 m²) | sığınak + depo |
| `zemin_kat` | blok INSERT | 264 | ZEMİN KAT PLANI Ö:1/50 | 19.08 × 35.05 m (516.6 m²) | 2 dükkân + teras |
| `normal_kat` | blok INSERT | 859 | NORMAL KAT PLANI Ö:1/50 | 19.08 × 35.05 m (510.2 m²) | 2 daire/kat |
| `pafta_4` | doğrudan modelspace | 100 | — | 19.76 × 33.14 m (531.3 m²) | ⚠️ sadece 3 oda poligonu |
| `pafta_5` | doğrudan modelspace | 106 | — | 19.76 × 33.14 m (499.4 m²) | ⚠️ sadece 4 oda poligonu |
| `pafta_6` | doğrudan modelspace | 813 | — | 19.76 × 33.14 m (500.4 m²) | 36 kapı bloğu |

**Yorum:** Alt sıra, üst sıranın **daha yeni bir revizyonu** gibi görünüyor
(kontur 35.05 m → 33.14 m kısalmış, asansör 2.15 m → 2.24 m büyümüş) ama
**henüz tamamlanmamış**: `pafta_4` ve `pafta_5`'te iç bölme (oda) çizimleri yok.
Üst sıra ölçülendirmeli + alan etiketli olduğu için **metraj/3B için asıl kaynak
üst sıradır**.

---

## 3. Katman envanteri ve anlamları

Modelspace'te 803 entity / 15 katman; INSERT'ler açıldığında **2.362 ring** / 18 katman.

| Katman | Ring (tümü) | Kapalı | Ne | 3B'de kullanımı |
|---|---|---|---|---|
| `0` | 1.494 | 1.236 | Kapı bloğu (`kp_*`) detayları, ölçü çizgileri | atılır |
| `C_merdiven` | 240 | 228 | **Merdiven basamakları** (40 × 3 pafta) | basamak extrude |
| `C_kolon` | 211 | 211 | **Kolon kesitleri** (4 noktalı dikdörtgen) | ✅ direkt extrude |
| `C_pencere` | 100 | 100 | **Pencere boşlukları** (20 cm kalınlık) | ✅ duvardan CSG ile çıkarılır |
| `dvr_kaba` / `dvr_siva` | 92 / 92 | 92 / 92 | Kapı eşiği dolgusu (`kp_*` içinde) | ✅ **kapı boşluğu** olarak kullanılır |
| `C_oda` | 88 | 87 | **İç mekân / oda poligonları** | ✅ duvar türetmede boşluk |
| `mekanadi` | 79 MTEXT | — | Oda adı + alan (örn. `OTURMA_OD. 28.53 m²`) | metraj |
| `ic_olcu` | 231 DIMENSION | — | İç ölçülendirme (medyan 250 cm) | birim doğrulama |
| `B_balkon` | 27 | 27 | Balkonlar | ✅ extrude (döşeme kalınlığı) |
| `Asansör` | 12 | 12 | Asansör kuyusu (2.15 / 2.24 m kare) | ✅ extrude |
| `HavaBaca` / `C_baca` | 9 / 8 | 9 / 8 | Hava bacası / baca | ✅ extrude |
| `Bina_kontur` | 6 | 6 | **Bina dış konturu** (16–36 nokta) | ✅ döşeme + duvar dış sınırı |
| `C_pafta` | 6 | 6 | Pafta çerçevesi (63 × 60 m) | atılır |
| `Merdiven` / `Merd+Koridor` | 2 / 5 | 2 / 1 | Merdiven evi + koridor boşluğu | ✅ duvar türetmede boşluk |
| `C_kapi` | 2 | 2 | Serbest çizilmiş kapı (blok dışı) | kapı boşluğu |

### ⚠️ Duvar katmanı yok
Çizimde `C_duvar` / `duvar` / `WALL` benzeri bir katman **bulunmuyor**. Dolayısıyla:

```
duvar_katısı = Bina_kontur  −  ( C_oda ∪ Merdiven ∪ Merd+Koridor
                                 ∪ Asansör ∪ C_baca ∪ HavaBaca )
```

`cad2d.solid.walls_from_contour()` tam olarak bunu yapıyor. `normal_kat` için
sonuç: **60.8 m² taban alanı, 3.0 m yükseklik → 182.4 m³**; pencere (−11.0 m³)
ve kapı (−11.4 m³) boşlukları CSG ile çıktıktan sonra **160.0 m³**.

---

## 4. Mimari eleman ölçüleri (otomatik çıkarılan)

**Kolonlar** (`C_kolon`, 211 adet, hepsi 4 noktalı dikdörtgen):

| Kesit (cm) | Adet |
|---|---|
| 30 × 70 | 173 |
| 30 × 140 | 20 |
| 30 × 120 | 14 |
| 30 × 95 | 4 |

**Kapılar** (`C_kapi` → `kp_*` blokları):

| Blok | Blok genişliği | Anlamı | Adet (modelspace) |
|---|---|---|---|
| `kp_90` | 97 birim | 90 cm kanat | 20 |
| `kp_100` | 105 birim | 100 cm kanat | 12 |
| `kp_90_20` | 97 birim | 90 cm + 20 cm varyant | 4 |
| `kp_90_10`, `kp_100_20`, `kp_100_15` | — | tanımlı, kullanılmamış | 0 |

Bloklar **iç içe**: `kp_100_15` → `INSERT kp_100`. Kapılar `rot = 0/90/180/270`
ve `xscale = ±1` (ayna) ile yerleştirilmiş → flatten sırasında matris zinciri
doğru kurulmalı (`manifold3d`/`ezdxf` satır-vektör kuralı).

**Pencereler** (`C_pencere`): kalınlık hep **20 cm** (= duvar), genişlik
140 / 150 / 240 / 300 cm.

**Asansör:** 2.15 × 2.15 m (rev. A, etiket 4.64 m²) / 2.24 × 2.24 m (rev. B, 5.00 m²).

**Diğer:** 32 adet `CIRCLE` (r = 13.1 cm) + 32 adet `TEXT` (1…32) — bunlar
Y ≈ 14.000–16.400 bandında iki 4×4 tablo hâlinde; büyük olasılıkla **kapı/pencere
numara tablosu**, daire numarası değil.

---

## 5. Oda / alan dökümü (`mekanadi` katmanı, 79 etiket)

**Bodrum:** SIĞINAK 253.45 m² · DEPO 185.17 m² · MERDIVEN 12.19 · YANGIN_MER. 12.19 ·
ASANSÖR 4.64 · KORIDOR 32.24 · SUDEPSU 13.13 · SISTEM.HAB.OD. 6.02

**Zemin:** DÜKKAN_1 217.23 m² · DÜKKAN_2 184.30 m² · TERAS 102.03 m² ·
KAPICIOD. 12.24 · WC 3.28 · MERDIVEN 12.19 · YANGIN_MER. 12.19 · ASANSÖR 4.64 ·
KORIDOR 23.58 · BALKON 17.62 (×2) · BALKON 3.18 (×2)

**Normal kat** (daire başına, 2 daire/kat):
OTURMA_OD. 28.53 · EB.YATAKOD 14.45 · YATAKOD_1 9.04 · YATAKOD_2 11.25 ·
MUTFAK 11.25 · BANYO+WC 4.08 / 3.87 · EB.BAN+WC 3.29 / 3.23 · GIRIŞ_HOLÜ 6.21 ·
BALKON 11.75 + 3.24 · HAV_BAC 1.05 / 0.72 · MERDİVEN 12.06 · YANGIN_MER. 12.06 ·
KORIDOR 58.65 · ASANSÖR 4.64

---

## 6. 3B dönüşüm için hazırlık notları

Hattı çalıştıran iki tuzak (ikisi de `src/cad2d/` içinde çözüldü):

1. **ezdxf `Matrix44` satır-vektör kuralı.**
   `p' = p @ M` ve **öteleme son SATIRDA** (`M[3,:3]`), son sütunda değil.
   Ayrıca `np.asarray(Matrix44)` çalışmaz → `M.get_row(i)` kullanılmalı.
   İç içe INSERT'lerde zincir `M_iç @ M_dış` sırasıyla kurulmalı.

2. **shapely ↔ manifold3d yön uyumsuzluğu.**
   `shapely.difference()` dış halkayı **saat yönünde** (negatif alan), delikleri
   **saat yönünün tersine** (pozitif) verir. `manifold3d.CrossSection(..., FillRule.Positive)`
   ise tam tersini bekler. Düzeltilmezse sonuç sessizce **boş gövde**
   (`Error.InvalidConstruction`) olur — duvar 41 delikli olduğu için bu dosyada
   tam da bu durum oluşuyordu.

### Çalışan komutlar

```bash
# paftaları listele + birim tespiti
python scripts/build3d.py --list

# tek kat -> GLB + three.js HTML
python scripts/build3d.py --floor normal_kat --openings \
       --wall-height 300 --slab 20 --out out/normal_kat.glb

# hepsi (6 pafta) + index.html
python scripts/build3d.py --all --openings --out out/model.glb

# 2B plan önizlemesi (PNG)
python scripts/preview_dxf.py data/kavaklik_01.dxf -o out/preview.png
python scripts/preview_dxf.py data/kavaklik_01.dxf \
       --bbox 12600,6000,18900,12000 -o out/plan_normal_kat.png
```

### `normal_kat` için üretilen gövdeler (3.0 m kat yüksekliği, 20 cm döşeme)

| Parça | Hacim m³ | Üçgen |
|---|---|---|
| döşeme | 102.03 | 108 |
| duvar | 160.04 | 2.128 |
| kolon | 28.89 | 468 |
| balkon | 23.98 | 96 |
| asansör | 27.84 | 24 |
| baca | 18.78 | 120 |
| merdiven | 33.11 | 100 |

---

## 7. Eksikler / belirsizlikler

- **Kat yüksekliği DXF'te yok.** `$THICKNESS = 0`, `$ELEVATION = 0`. Varsayılan
  300 cm olarak alındı; `--wall-height` ile değiştirilebilir.
- **Kat sayısı / daire sayısı belirsiz.** `normal_kat` 2 daire içeriyor; 32
  numaralı tablo daire değil, kapı/pencere cetveli gibi duruyor. Kaç normal kat
  tekrar ediyor bilgisi DXF'te yok.
- **Duvar kalınlığı tek tip değil.** Pencereler 20 cm gösteriyor; `dvr_kaba`/
  `dvr_siva` (kapı eşiği) katmanları **iç/dış** ayrımı ima ediyor ama blok
  içi detay olduğu için duvar katmanı olarak kullanılamıyor.
- **Alt sıra (revizyon B) eksik:** `pafta_4` / `pafta_5` iç bölme çizimleri
  yok → duvar türetme bu paftalarda anlamlı sonuç vermez (pafta_4'te 502 m²
  "duvar" çıkıyor, neredeyse tüm kontur dolu).
- **Z bilgisi yok:** tüm geometri `Z = 0` düzleminde, saf 2B çizim.
