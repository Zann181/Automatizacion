#!/bin/bash
# Script simple para Raspberry Pi 2 sin WiFi.
# Detecta cable Ethernet en eth0 y muestra/guarda lo que llega desde el PLC.
#
# Uso:
#   sudo bash leer_log_plc.sh
#   sudo bash leer_log_plc.sh 192.168.0.1

PLC_IP="${1:-}"
IFACE="eth0"
LOG_DIR="logs"
FECHA="$(date +%Y%m%d_%H%M%S)"
LOG_FILE="$LOG_DIR/plc_$FECHA.log"
PCAP_FILE="$LOG_DIR/plc_$FECHA.pcap"
TCPDUMP_PID=""

mkdir -p "$LOG_DIR"

if [ "$(id -u)" -ne 0 ]; then
    echo "ERROR: ejecuta el script con sudo:"
    echo "sudo bash leer_log_plc.sh"
    exit 1
fi

if [ ! -d "/sys/class/net/$IFACE" ]; then
    echo "ERROR: no existe la interfaz $IFACE"
    echo "Interfaces disponibles:"
    ls /sys/class/net
    exit 1
fi

if ! command -v tcpdump >/dev/null 2>&1; then
    echo "ERROR: tcpdump no esta instalado."
    echo "Instalalo antes en la Raspberry con:"
    echo "sudo apt-get install tcpdump"
    exit 1
fi

echo "=========================================="
echo " Lector de log PLC por Ethernet"
echo " Interfaz: $IFACE"
echo " PLC IP  : ${PLC_IP:-sin filtro}"
echo " Log     : $LOG_FILE"
echo " PCAP    : $PCAP_FILE"
echo "=========================================="
echo ""

echo "Esperando conexion Ethernet en $IFACE..."
while true; do
    CARRIER="$(cat /sys/class/net/$IFACE/carrier 2>/dev/null || echo 0)"
    if [ "$CARRIER" = "1" ]; then
        break
    fi
    sleep 1
done

echo "Ethernet conectado."

if [ -n "$PLC_IP" ]; then
    echo "Esperando respuesta del PLC $PLC_IP..."
    while ! ping -I "$IFACE" -c 1 -W 1 "$PLC_IP" >/dev/null 2>&1; do
        sleep 1
    done
    echo "PLC detectado en $PLC_IP."
    FILTER="src host $PLC_IP"
else
    FILTER=""
fi

echo "Inicio: $(date)" >> "$LOG_FILE"
echo "Interfaz: $IFACE" >> "$LOG_FILE"
echo "PLC IP: ${PLC_IP:-sin filtro}" >> "$LOG_FILE"
echo "" >> "$LOG_FILE"

echo ""
echo "Leyendo datos. Presiona Ctrl+C para salir."
echo ""

cerrar() {
    if [ -n "$TCPDUMP_PID" ]; then
        kill "$TCPDUMP_PID" 2>/dev/null
        wait "$TCPDUMP_PID" 2>/dev/null
    fi
    echo ""
    echo "Log guardado en: $LOG_FILE"
    echo "Captura guardada en: $PCAP_FILE"
}
trap cerrar EXIT
trap "exit 0" INT TERM

if [ -n "$FILTER" ]; then
    tcpdump -i "$IFACE" -nn -s 0 -w "$PCAP_FILE" "$FILTER" &
    TCPDUMP_PID=$!
    tcpdump -i "$IFACE" -nn "$FILTER" | tee -a "$LOG_FILE"
else
    tcpdump -i "$IFACE" -nn -s 0 -w "$PCAP_FILE" &
    TCPDUMP_PID=$!
    tcpdump -i "$IFACE" -nn | tee -a "$LOG_FILE"
fi

exit 0
