# Script PowerShell para compartir Internet del PC a la Raspberry Pi
# ============================================================
# compartir_internet_rpi.ps1
#
# Este script configura Windows para compartir la conexion WiFi
# del PC con la Raspberry Pi conectada por cable Ethernet.
#
# RESULTADO: La RPi obtendra internet a traves del PC,
# permitiendo instalar paquetes con apt-get.
#
# REQUISITO: Ejecutar como Administrador
# ============================================================

Write-Host "==================================================" -ForegroundColor Cyan
Write-Host "  Compartir Internet WiFi -> Ethernet -> RPi      " -ForegroundColor Cyan
Write-Host "==================================================" -ForegroundColor Cyan
Write-Host ""

# Verificar que se esta ejecutando como Administrador
if (-NOT ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Host "[ERROR] Debes ejecutar este script como Administrador." -ForegroundColor Red
    Write-Host "Haz clic derecho en PowerShell -> 'Ejecutar como administrador'" -ForegroundColor Yellow
    exit 1
}

# Obtener adaptadores de red
$adapters = Get-NetAdapter | Where-Object { $_.Status -eq "Up" }

Write-Host "Adaptadores de red disponibles:" -ForegroundColor Yellow
$adapters | ForEach-Object { Write-Host "  - $($_.Name) [$($_.InterfaceDescription)]" }
Write-Host ""

# Detectar WiFi (fuente de internet)
$wifi = Get-NetAdapter | Where-Object { $_.Name -like "*Wi*" -or $_.Name -like "*WiFi*" -or $_.Name -like "*Wireless*" } | Select-Object -First 1
# Detectar Ethernet (hacia la RPi)
$eth  = Get-NetAdapter | Where-Object { $_.Name -like "*Ethernet*" -or $_.Name -like "*Local*" } | Select-Object -First 1

if (-not $wifi) {
    Write-Host "[AVISO] No se detecto adaptador WiFi automaticamente." -ForegroundColor Yellow
    Write-Host "Lista de adaptadores:" -ForegroundColor Yellow
    Get-NetAdapter | ForEach-Object { Write-Host "  - $($_.Name)" }
    $wifiName = Read-Host "Ingresa el nombre exacto del adaptador WiFi (fuente de internet)"
    $wifi = Get-NetAdapter -Name $wifiName
}

if (-not $eth) {
    Write-Host "[AVISO] No se detecto adaptador Ethernet automaticamente." -ForegroundColor Yellow
    $ethName = Read-Host "Ingresa el nombre exacto del adaptador Ethernet (hacia la RPi)"
    $eth = Get-NetAdapter -Name $ethName
}

Write-Host "Configurando:" -ForegroundColor Green
Write-Host "  Internet (WiFi):  $($wifi.Name)" -ForegroundColor White
Write-Host "  Hacia RPi (Eth):  $($eth.Name)"  -ForegroundColor White
Write-Host ""

# Habilitar ICS (Internet Connection Sharing) via netsh
$wifiGuid = (Get-NetAdapter -Name $wifi.Name).InterfaceGuid
$ethGuid  = (Get-NetAdapter -Name $eth.Name).InterfaceGuid

# Usar regutil para ICS (funciona en todas las versiones de Windows)
try {
    # Metodo 1: Via ICS Manager (COM)
    $netShare = New-Object -ComObject HNetCfg.HNetShare
    $connections = $netShare.EnumEveryConnection()

    foreach ($conn in $connections) {
        $props = $netShare.NetConnectionProps($conn)
        $config = $netShare.INetSharingConfigurationForINetConnection($conn)

        if ($props.Name -eq $wifi.Name) {
            # Habilitar ICS en la interfaz WiFi (compartir desde aqui)
            $config.EnableSharing(0)   # 0 = PUBLIC (fuente)
            Write-Host "  ✓ ICS habilitado en: $($wifi.Name) (fuente)" -ForegroundColor Green
        }
        if ($props.Name -eq $eth.Name) {
            # Habilitar ICS en Ethernet (dar internet a RPi)
            $config.EnableSharing(1)   # 1 = PRIVATE (destino)
            Write-Host "  ✓ ICS habilitado en: $($eth.Name) (destino)" -ForegroundColor Green
        }
    }
} catch {
    Write-Host "[AVISO] Metodo COM falló. Intentando via netsh..." -ForegroundColor Yellow

    # Metodo 2: Via netsh (alternativo)
    netsh interface ip set address "$($eth.Name)" dhcp
    Write-Host "  Configura ICS manualmente:" -ForegroundColor Yellow
    Write-Host "  1. Abre Panel de Control -> Redes -> Cambiar configuracion del adaptador" -ForegroundColor White
    Write-Host "  2. Clic derecho en '$($wifi.Name)' -> Propiedades -> Uso Compartido" -ForegroundColor White
    Write-Host "  3. Marca 'Permitir que otros usuarios de la red se conecten...'" -ForegroundColor White
    Write-Host "  4. Selecciona '$($eth.Name)' en el desplegable" -ForegroundColor White
    Write-Host "  5. Acepta. La RPi obtendra internet automaticamente." -ForegroundColor White
}

Write-Host ""
Write-Host "==================================================" -ForegroundColor Cyan
Write-Host " Configuracion ICS completada"                       -ForegroundColor Cyan
Write-Host "==================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "En la Raspberry Pi, ejecuta:" -ForegroundColor Yellow
Write-Host "  sudo dhclient eth0          # Obtener IP automatica"    -ForegroundColor White
Write-Host "  ping 8.8.8.8               # Verificar internet"        -ForegroundColor White
Write-Host "  sudo apt-get update"                                      -ForegroundColor White
Write-Host "  sudo apt-get install -y build-essential g++ make \"" -ForegroundColor White
Write-Host "      libsqlite3-dev sqlite3 libssl-dev openssl libopen62541-dev" -ForegroundColor White
Write-Host ""
Write-Host "Cuando termines, restaura la IP fija de Ethernet:" -ForegroundColor Yellow
Write-Host "  sudo bash ~/ProyectoOPCUA/scripts/configurar_ethernet.sh" -ForegroundColor White
Write-Host ""
