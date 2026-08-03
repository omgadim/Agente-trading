# ============================================================================
#  Auto-arranque tras reiniciar el VPS (Windows, sin Docker).
#  Lo ejecuta el Programador de Tareas "al iniciar sesion". Abre MT5 si no esta
#  corriendo, espera a que conecte, y lanza el bot para cada instrumento activo.
#
#  REQUISITO: define UNA vez estas variables de entorno de USUARIO (persisten
#  tras reinicio) con setx (ver instrucciones). NO se guardan en el repo:
#     setx MT5_PASSWORD "tu_password_master"
#     setx TELEGRAM_TOKEN "tu_token"
#     setx TELEGRAM_CHAT_ID "tu_chat_id"
#  Y tener MT5 configurado para auto-login (Herramientas>Opciones>Guardar cuenta).
# ============================================================================
$ErrorActionPreference = "Continue"
Set-Location -Path $PSScriptRoot
$env:PYTHONPATH = Join-Path $PSScriptRoot 'src'

# --- Ruta al terminal MT5 (AJUSTA si tu broker instala en otra carpeta) ------
$Mt5Exe = "C:\Program Files\MetaTrader 5\terminal64.exe"

# --- 1) Asegurar que MT5 este abierto ----------------------------------------
if (-not (Get-Process -Name terminal64 -ErrorAction SilentlyContinue)) {
    if (Test-Path $Mt5Exe) {
        Write-Host "Abriendo MetaTrader 5..." -ForegroundColor Cyan
        Start-Process $Mt5Exe
        Write-Host "Esperando 40s a que MT5 conecte y auto-loguee..." -ForegroundColor Cyan
        Start-Sleep -Seconds 40
    } else {
        Write-Host "AVISO: no encuentro MT5 en $Mt5Exe. Abrelo a mano o ajusta la ruta." -ForegroundColor Yellow
    }
} else {
    Write-Host "MT5 ya esta corriendo." -ForegroundColor DarkGray
}

# --- 2) Verificar credenciales -----------------------------------------------
if (-not $env:MT5_PASSWORD) {
    Write-Host "ERROR: falta MT5_PASSWORD (configurala con setx). No se lanza el bot." -ForegroundColor Red
    exit 1
}

# --- 3) Lanzar una instancia por instrumento activo --------------------------
$instruments = python -m examples.list_enabled
if (-not $instruments) {
    Write-Host "No hay instrumentos activos (enabled:true) en config.yaml" -ForegroundColor Red
    exit 1
}
Write-Host "Instrumentos activos:" -ForegroundColor Cyan
$instruments | ForEach-Object { Write-Host "  - $_" }

foreach ($inst in $instruments) {
    Write-Host "Lanzando $inst..." -ForegroundColor Green
    Start-Process powershell -ArgumentList `
        "-NoExit","-ExecutionPolicy","Bypass","-File",".\start_live.ps1","-Instrument",$inst
    Start-Sleep -Seconds 3
}
Write-Host "Auto-arranque completado." -ForegroundColor Green
