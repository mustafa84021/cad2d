# Tek komutluk kurulum (Windows PowerShell)
#
#   .\setup.ps1
#
# "Bu betiğe izin yok" derse, yönetici olarak bir kez:
#   Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
#
# Yapar: .venv oluşturur, bağımlılıkları kurar, data/ + out/ klasörlerini açar,
#        data/ içinde DXF varsa pafta listesini yazdırır.

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

Write-Host "==> Sanal ortam" -ForegroundColor Cyan
if (-not (Test-Path .venv)) {
    python -m venv .venv
    Write-Host "    .venv olusturuldu"
} else {
    Write-Host "    .venv zaten var"
}

Write-Host "==> Bagimliliklar (requirements.txt)" -ForegroundColor Cyan
& .\.venv\Scripts\python.exe -m pip install -q --upgrade pip
& .\.venv\Scripts\python.exe -m pip install -q -r requirements.txt
Write-Host "    ezdxf / shapely / manifold3d / trimesh / matplotlib hazir"

Write-Host "==> Klasorler" -ForegroundColor Cyan
New-Item -ItemType Directory -Force -Path data, out | Out-Null
Write-Host "    data\  (DXF'lerini buraya koy)"
Write-Host "    out\   (ciktilar buraya yazilir)"

Write-Host ""
$dxf = Get-ChildItem -Path data -Filter *.dxf -File -ErrorAction SilentlyContinue
if ($dxf) {
    Write-Host "==> data\ icinde DXF bulundu, pafta listesi:" -ForegroundColor Cyan
    Write-Host ""
    foreach ($f in $dxf) {
        if ($dxf.Count -gt 1) { Write-Host "--- $($f.Name)" }
        & .\.venv\Scripts\python.exe scripts\build3d.py --dxf $f.FullName --list
    }
    Write-Host ""
    Write-Host "Siradaki adim:" -ForegroundColor Yellow
    Write-Host "  .\.venv\Scripts\python.exe scripts\build3d.py --floor <pafta_adi> --openings --out out\model.glb"
} else {
    Write-Host "==> data\ bos." -ForegroundColor Yellow
    Write-Host "    DXF dosyani (orn. kavaklik_01.dxf) data\ klasorune kopyala, sonra:"
    Write-Host ""
    Write-Host "      .\.venv\Scripts\python.exe scripts\build3d.py --list"
    Write-Host ""
}
