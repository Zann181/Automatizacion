# ============================================================
# deploy_to_rpi.ps1 — Enviar cambios a la Raspberry Pi desde Windows
#
# Prerequisito: OpenSSH instalado en Windows (viene con Windows 10/11)
#               La RPi debe estar en la misma red que esta PC.
#
# Uso:
#   .\scripts\deploy_to_rpi.ps1 -RpiIp "192.168.X.X" -RpiUser "pi"
#
# Ejemplo tipico (RPi conectada por USB/Ethernet compartido):
#   .\scripts\deploy_to_rpi.ps1 -RpiIp "192.168.137.x" -RpiUser "pi"
# ============================================================

param(
    [Parameter(Mandatory=$false)]
    [string]$RpiIp   = "192.168.137.2",     # IP de la RPi en la red compartida de Windows
    [string]$RpiUser = "pi",
    [string]$RemoteDir = "~/ProyectoOPCUA"
)

$ProjectRoot = Split-Path $PSScriptRoot -Parent
Write-Host ""
Write-Host "======================================" -ForegroundColor Cyan
Write-Host "  Deploy -> Raspberry Pi" -ForegroundColor Cyan
Write-Host "  Destino : $RpiUser@$RpiIp:$RemoteDir" -ForegroundColor Cyan
Write-Host "======================================" -ForegroundColor Cyan
Write-Host ""

# ---- 1. Copiar archivos actualizados del proyecto ----
Write-Host "[1/3] Copiando directorios del proyecto (src, include, web, scripts)..." -ForegroundColor Yellow

# Crear directorios remotos
ssh "$RpiUser@$RpiIp" "mkdir -p $RemoteDir"

# Copiar directorios completos
scp -r "$ProjectRoot\src"      "${RpiUser}@${RpiIp}:${RemoteDir}/"
scp -r "$ProjectRoot\include"  "${RpiUser}@${RpiIp}:${RemoteDir}/"
scp -r "$ProjectRoot\web"      "${RpiUser}@${RpiIp}:${RemoteDir}/"
scp -r "$ProjectRoot\scripts"  "${RpiUser}@${RpiIp}:${RemoteDir}/"

Write-Host "  ✓ Archivos copiados." -ForegroundColor Green

# ---- 2. Ejecutar script de actualizacion en la RPi ----
Write-Host ""
Write-Host "[2/3] Ejecutando actualizacion en la Raspberry Pi..." -ForegroundColor Yellow

ssh "$RpiUser@$RpiIp" "cd $RemoteDir && chmod +x scripts/actualizar_rpi.sh && sudo bash scripts/actualizar_rpi.sh"

Write-Host "  ✓ Script ejecutado." -ForegroundColor Green

# ---- 3. Verificar estado ----
Write-Host ""
Write-Host "[3/3] Verificando configuracion en la DB..." -ForegroundColor Yellow
ssh "$RpiUser@$RpiIp" "sqlite3 $RemoteDir/config_plc.db 'SELECT ip, port, endpoint FROM config_opc WHERE id=1;'"

Write-Host ""
Write-Host "======================================" -ForegroundColor Green
Write-Host "  ✓ Deploy completado!" -ForegroundColor Green
Write-Host "  Dashboard: http://${RpiIp}:8080" -ForegroundColor Green
Write-Host "======================================" -ForegroundColor Green
Write-Host ""
