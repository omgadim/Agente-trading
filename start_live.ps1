# ============================================================================
#  Arranque de UNA instancia en vivo (Windows / VPS, sin Docker)
#  Uso:
#     .\start_live.ps1                 -> instrumento base (Oro)
#     .\start_live.ps1 -Instrument NAS100
#
#  Pide la contraseña MASTER de MT5 al arrancar (NO se guarda en disco ni en el
#  repo). Edita Login y Server una vez con los datos de tu cuenta.
# ============================================================================
param(
    [string]$Instrument = "",
    [int]$Interval = 60
)

# --- Datos de tu cuenta MT5 (edítalos una vez) ------------------------------
$Login  = '153546'          # <-- número de cuenta MT5
$Server = 'VexPro-Server'   # <-- servidor del broker

# --- No toques debajo de esta línea -----------------------------------------
Set-Location -Path $PSScriptRoot
$env:PYTHONPATH = Join-Path $PSScriptRoot 'src'

$label = if ($Instrument) { $Instrument } else { "Oro (base)" }
Write-Host "Instrumento: $label" -ForegroundColor Cyan
Write-Host "Cuenta:  $Login @ $Server" -ForegroundColor Cyan
# Contrasena: si ya viene en la variable de entorno MT5_PASSWORD (modo desatendido/
# auto-arranque) se usa esa; si no, se pide por teclado (modo manual).
if (-not $env:MT5_PASSWORD) {
    Write-Host "IMPORTANTE: usa la contrasena MASTER (no la de investor)." -ForegroundColor Yellow
    $sec = Read-Host 'Contrasena MASTER de MT5' -AsSecureString
    $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($sec)
    $env:MT5_PASSWORD = [Runtime.InteropServices.Marshal]::PtrToStringAuto($bstr)
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
} else {
    Write-Host "Contrasena tomada de la variable de entorno MT5_PASSWORD." -ForegroundColor DarkGray
}
$env:MT5_LOGIN  = $Login
$env:MT5_SERVER = $Server

Write-Host "`nRecordatorio: activa 'Algo Trading' en MT5 (Ctrl+E, circulo verde)." -ForegroundColor Yellow
Write-Host "Lanzando...`n" -ForegroundColor Green

if ($Instrument) {
    python -m examples.run_live --mode live --interval $Interval --instrument $Instrument
} else {
    python -m examples.run_live --mode live --interval $Interval
}

$env:MT5_PASSWORD = $null
