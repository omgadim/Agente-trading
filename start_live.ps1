# ============================================================================
#  Arranque del sistema en vivo (Windows / VPS, sin Docker)
#  Uso:  clic derecho -> "Ejecutar con PowerShell"   o   .\start_live.ps1
#
#  Pide la contraseña MASTER de MT5 al arrancar (NO se guarda en disco ni en
#  el repo). Edita LOGIN y SERVER una sola vez con los datos de tu cuenta.
# ============================================================================

# --- Datos de tu cuenta MT5 (edítalos una vez) ------------------------------
$Login  = '153546'          # <-- número de cuenta MT5
$Server = 'VexPro-Server'   # <-- servidor del broker
$Interval = 60              # <-- segundos entre revisiones

# --- No toques debajo de esta línea -----------------------------------------
Set-Location -Path $PSScriptRoot

Write-Host "Cuenta:  $Login @ $Server" -ForegroundColor Cyan
Write-Host "IMPORTANTE: usa la contraseña MASTER (no la de investor)." -ForegroundColor Yellow
$sec = Read-Host 'Contrasena MASTER de MT5' -AsSecureString
$bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($sec)
$plain = [Runtime.InteropServices.Marshal]::PtrToStringAuto($bstr)
[Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)

$env:MT5_LOGIN    = $Login
$env:MT5_SERVER   = $Server
$env:MT5_PASSWORD = $plain

Write-Host "`nRecordatorio: activa 'Algo Trading' en MT5 (Ctrl+E, circulo verde)." -ForegroundColor Yellow
Write-Host "Lanzando operativa en vivo...`n" -ForegroundColor Green

python -m examples.run_live --mode live --interval $Interval

# limpia la contraseña de la sesion al terminar
$env:MT5_PASSWORD = $null
$plain = $null
