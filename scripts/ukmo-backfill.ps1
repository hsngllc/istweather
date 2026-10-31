# UKMO Global geçmiş nokta çıkarımını Windows'ta arka planda başlatır veya durdurur.
# Geçici çözüm: Docker Desktop kurulana kadar (spec §4 Windows notu). Çıktı git dışı .data\ altında.
# İş kaldığı yerden devam eder; durdurup yeniden başlatmak güvenlidir.
#
#   powershell -ExecutionPolicy Bypass -File scripts\ukmo-backfill.ps1            # başlat
#   powershell -ExecutionPolicy Bypass -File scripts\ukmo-backfill.ps1 -Workers 16
#   powershell -ExecutionPolicy Bypass -File scripts\ukmo-backfill.ps1 -Stop      # durdur
param(
    [int]$Workers = 32,
    [switch]$Stop
)

$root = Split-Path -Parent $PSScriptRoot
$out = Join-Path $root ".data\ukmo_global"
$pidFile = Join-Path $out "backfill.pid"
New-Item -ItemType Directory -Force $out | Out-Null

if ($Stop) {
    if (Test-Path $pidFile) {
        $id = Get-Content $pidFile
        # Süreç havuzundaki işçiler de dursun diye süreç ağacı sonlandırılır.
        taskkill /PID $id /T /F | Out-Null
        Remove-Item $pidFile
        "Durduruldu (PID $id)."
    } else {
        "Çalışan bir iş bulunamadı."
    }
    return
}

if (Test-Path $pidFile) {
    $old = Get-Process -Id (Get-Content $pidFile) -ErrorAction SilentlyContinue
    if ($old) {
        "Zaten çalışıyor (PID $($old.Id)). Log: $out\backfill.log"
        return
    }
}

$python = Join-Path $root ".venv\Scripts\python.exe"
$arguments = @(
    "-I", "-m", "hava.ingest.archive.ukmo",
    "--out", "`"$out`"",
    "--region", "`"$(Join-Path $root 'config\region.istanbul.yaml')`"",
    "--workers", $Workers,
    "--follow"
)
$p = Start-Process -FilePath $python -ArgumentList $arguments -WorkingDirectory $root `
    -WindowStyle Hidden -PassThru `
    -RedirectStandardOutput (Join-Path $out "stdout.log") `
    -RedirectStandardError (Join-Path $out "stderr.log")
$p.Id | Set-Content $pidFile
"Başlatıldı (PID $($p.Id)). Log: $out\backfill.log"
