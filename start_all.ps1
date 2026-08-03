# ============================================================================
#  Lanza TODAS las instancias activas (instruments con enabled:true en config).
#  Abre una ventana de PowerShell por instrumento. Para activar/desactivar uno,
#  cambia su `enabled` en config/config.yaml y vuelve a ejecutar esto.
# ============================================================================
Set-Location -Path $PSScriptRoot
$env:PYTHONPATH = Join-Path $PSScriptRoot 'src'

$instruments = python -m examples.list_enabled
if (-not $instruments) {
    Write-Host "No hay instrumentos activos (enabled:true) en config.yaml" -ForegroundColor Red
    exit
}
Write-Host "Instrumentos activos:" -ForegroundColor Cyan
$instruments | ForEach-Object { Write-Host "  - $_" }
Write-Host "`nSe abrira una ventana por cada uno. Cada una pedira la contrasena MASTER." -ForegroundColor Yellow
Write-Host "Recuerda: 'Algo Trading' verde en MT5 (Ctrl+E).`n" -ForegroundColor Yellow

foreach ($inst in $instruments) {
    Start-Process powershell -ArgumentList "-NoExit","-File",".\start_live.ps1","-Instrument",$inst
    Start-Sleep -Seconds 2
}
