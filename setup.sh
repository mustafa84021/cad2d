#!/usr/bin/env bash
# Tek komutluk kurulum (macOS / Linux / WSL / Git Bash)
#
#   ./setup.sh
#
# Yapar: .venv oluşturur, bağımlılıkları kurar, data/ + out/ klasörlerini açar,
#        data/ içinde DXF varsa pafta listesini yazdırır.
set -euo pipefail
cd "$(dirname "$0")"

echo "==> Sanal ortam"
if [ ! -d .venv ]; then
    python3 -m venv .venv
    echo "    .venv oluşturuldu"
else
    echo "    .venv zaten var"
fi

echo "==> Bağımlılıklar (requirements.txt)"
./.venv/bin/python -m pip install -q --upgrade pip
./.venv/bin/python -m pip install -q -r requirements.txt
echo "    ezdxf / shapely / manifold3d / trimesh / matplotlib hazır"

echo "==> Klasörler"
mkdir -p data out
echo "    data/  (DXF'lerini buraya koy)"
echo "    out/   (çıktılar buraya yazılır)"

echo
if ls data/*.dxf >/dev/null 2>&1; then
    echo "==> data/ içinde DXF bulundu, pafta listesi:"
    echo
    for f in data/*.dxf; do
        if [ "$(ls data/*.dxf | wc -l)" -gt 1 ]; then echo "--- $f"; fi
        ./.venv/bin/python scripts/build3d.py --dxf "$f" --list
    done
    echo
    echo "Sıradaki adım:"
    echo "  ./.venv/bin/python scripts/build3d.py --floor <pafta_adı> --openings --out out/model.glb"
else
    echo "==> data/ boş."
    echo "    DXF dosyanı (örn. kavaklik_01.dxf) data/ klasörüne kopyala, sonra:"
    echo
    echo "      ./.venv/bin/python scripts/build3d.py --list"
    echo
    echo "    Windows isen bunun yerine: .\\setup.ps1"
fi
