#!/bin/bash
echo "=========================================================="
echo " Configurando Conexión Ethernet Directa (Industrial)"
echo " Raspberry Pi <-> PC via Cable Ethernet"
echo "=========================================================="

# Método 1: NetworkManager (nmcli) - Para Raspberry Pi OS Bookworm
if command -v nmcli &> /dev/null; then
    echo "[*] NetworkManager detectado. Usando nmcli..."
    
    # Eliminar perfil anterior si existe
    sudo nmcli connection delete "Conexion_Directa_PLC" 2>/dev/null && \
        echo "[*] Perfil anterior eliminado."

    # Crear nuevo perfil Ethernet estático en eth0
    sudo nmcli connection add \
        con-name "Conexion_Directa_PLC" \
        ifname eth0 \
        type ethernet \
        ipv4.method manual \
        ipv4.addresses "192.168.0.10/24" \
        ipv4.gateway "" \
        connection.autoconnect yes

    # Activar la conexión
    sudo nmcli connection up "Conexion_Directa_PLC"
    echo "[OK] Conexion activada via nmcli."

# Método 2: dhcpcd - Para Raspberry Pi OS Bullseye/Buster (legacy)
else
    echo "[*] nmcli no encontrado. Usando dhcpcd..."
    
    # Eliminar configuración anterior si existe
    sudo sed -i '/# === ETHERNET INDUSTRIAL ===/,/# === FIN ETHERNET INDUSTRIAL ===/d' /etc/dhcpcd.conf
    
    # Agregar IP estática para eth0 al final del archivo
    cat >> /etc/dhcpcd.conf << 'EOF'

# === ETHERNET INDUSTRIAL ===
interface eth0
static ip_address=192.168.0.10/24
# === FIN ETHERNET INDUSTRIAL ===
EOF
    
    # Reiniciar el servicio de red
    sudo systemctl restart dhcpcd
    echo "[OK] IP estática configurada via dhcpcd."
fi

echo ""
echo "=========================================================="
echo " ¡Configuración Completada!"
echo " IP Raspberry Pi (eth0): 192.168.0.10"
echo " IP PC (Ethernet 2):     192.168.0.1"
echo " Puerto OPC UA:          4840"
echo "=========================================================="
echo ""
echo "[*] Verificando conectividad..."
sleep 2
ping -c 3 192.168.0.1 && echo "[OK] ¡PC alcanzable! Ethernet funcionando." \
                        || echo "[ERROR] PC no responde. Verifica el cable y que el simulador esté corriendo."
