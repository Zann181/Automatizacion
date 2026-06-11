#!/bin/bash

# Configuración del Punto de Acceso
WIFI_SSID="PLC"
WIFI_PASS="123456789"
IP_ESTATICA="192.168.4.1/24"
INTERFAZ_WIFI="wlan0"

echo "========================================================"
echo " Configurando Raspberry Pi como Punto de Acceso (Hotspot)"
echo "========================================================"

if [ "$EUID" -ne 0 ]; then 
  echo "Por favor ejecuta este script como root usando: sudo bash setup_wifi.sh"
  exit
fi

# Método 1: NetworkManager (Moderno)
if command -v nmcli &> /dev/null; then
    echo "[+] NetworkManager detectado. Aplicando parche anti-desconexión..."
    
    # Limpiamos conexiones previas de hotspot
    nmcli connection delete hotspot &> /dev/null
    nmcli connection delete Hotspot &> /dev/null
    
    echo "========================================================"
    echo "¡ADVERTENCIA! Al ejecutar esto, tu SSH se desconectará."
    echo "La Raspberry Pi continuará trabajando sola en el fondo."
    echo "Espera 1 minuto, busca la red '$WIFI_SSID' en tu celular"
    echo "y entra a http://192.168.4.1:8080."
    echo "========================================================"
    
    # Encapsulamos los comandos peligrosos usando 'nohup' y los enviamos al fondo (&)
    # Así la Raspberry Pi los terminará sin importar que tu Windows se desconecte.
    nohup bash -c "
        nmcli device disconnect $INTERFAZ_WIFI
        sleep 2
        nmcli device wifi hotspot ifname $INTERFAZ_WIFI ssid $WIFI_SSID password $WIFI_PASS
        sleep 2
        nmcli connection modify Hotspot ipv4.addresses $IP_ESTATICA ipv4.method shared
        nmcli connection up Hotspot
    " > /dev/null 2>&1 &
    
    exit 0
fi

# Método 2: hostapd + dnsmasq (Antiguo)
echo "[-] NetworkManager no encontrado. Usando método clásico (hostapd)..."
# ... [El resto del script antiguo se mantiene igual]
apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y hostapd dnsmasq netfilter-persistent iptables-persistent
systemctl stop hostapd
systemctl stop dnsmasq

if [ ! -f /etc/dhcpcd.conf.bak ]; then
    cp /etc/dhcpcd.conf /etc/dhcpcd.conf.bak
fi
sed -i '/interface wlan0/d' /etc/dhcpcd.conf
sed -i '/static ip_address=192.168.4.1\/24/d' /etc/dhcpcd.conf
sed -i '/nohook wpa_supplicant/d' /etc/dhcpcd.conf

echo "interface wlan0" >> /etc/dhcpcd.conf
echo "    static ip_address=$IP_ESTATICA" >> /etc/dhcpcd.conf
echo "    nohook wpa_supplicant" >> /etc/dhcpcd.conf

mv /etc/dnsmasq.conf /etc/dnsmasq.conf.orig 2>/dev/null
cat > /etc/dnsmasq.conf <<EOF
interface=wlan0
dhcp-range=192.168.4.2,192.168.4.20,255.255.255.0,24h
EOF

cat > /etc/hostapd/hostapd.conf <<EOF
interface=wlan0
driver=nl80211
ssid=$WIFI_SSID
hw_mode=g
channel=7
wmm_enabled=0
macaddr_acl=0
auth_algs=1
ignore_broadcast_ssid=0
wpa=2
wpa_passphrase=$WIFI_PASS
wpa_key_mgmt=WPA-PSK
wpa_pairwise=TKIP
rsn_pairwise=CCMP
EOF

sed -i 's/#DAEMON_CONF=""/DAEMON_CONF="\/etc\/hostapd\/hostapd.conf"/g' /etc/default/hostapd

systemctl unmask hostapd
systemctl enable hostapd
systemctl start hostapd
systemctl start dnsmasq
service dhcpcd restart

echo "Reinicia la Raspberry Pi: sudo reboot"
