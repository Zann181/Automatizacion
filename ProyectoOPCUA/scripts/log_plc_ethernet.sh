#!/bin/bash
# Detecta conexion Ethernet del PLC y guarda todo el trafico entrante.
#
# Uso:
#   sudo ./scripts/log_plc_ethernet.sh
#   sudo ./scripts/log_plc_ethernet.sh 192.168.0.1
#   sudo ./scripts/log_plc_ethernet.sh 192.168.0.1 eth0
#
# Salida:
#   logs/plc_ethernet_YYYYmmdd_HHMMSS.log   resumen legible
#   logs/plc_ethernet_YYYYmmdd_HHMMSS.pcap  captura completa para Wireshark

set -e

PLC_IP="${1:-}"
IFACE="${2:-eth0}"
LOG_DIR="logs"
STAMP="$(date +%Y%m%d_%H%M%S)"
TEXT_LOG="$LOG_DIR/plc_ethernet_$STAMP.log"
PCAP_LOG="$LOG_DIR/plc_ethernet_$STAMP.pcap"
PCAP_PID=""

mkdir -p "$LOG_DIR"

if [ "$(id -u)" -ne 0 ]; then
    echo "[ERROR] Ejecuta con sudo para poder capturar trafico:"
    echo "        sudo $0 ${PLC_IP:-<ip_plc_opcional>} $IFACE"
    exit 1
fi

if [ ! -d "/sys/class/net/$IFACE" ]; then
    echo "[ERROR] No existe la interfaz '$IFACE'. Interfaces disponibles:"
    ls /sys/class/net
    exit 1
fi

if ! command -v tcpdump >/dev/null 2>&1; then
    echo "[ERROR] Falta tcpdump. Instala en la Raspberry con:"
    echo "        sudo apt-get install tcpdump"
    exit 1
fi

echo "============================================================"
echo " Monitor Ethernet PLC"
echo " Interfaz : $IFACE"
echo " PLC IP   : ${PLC_IP:-cualquier IP}"
echo " Texto    : $TEXT_LOG"
echo " PCAP     : $PCAP_LOG"
echo "============================================================"
echo ""

echo "[INFO] Esperando cable/conexion Ethernet en $IFACE..."
while true; do
    CARRIER="$(cat "/sys/class/net/$IFACE/carrier" 2>/dev/null || echo 0)"
    if [ "$CARRIER" = "1" ]; then
        break
    fi
    sleep 1
done

echo "[OK] Enlace Ethernet detectado en $IFACE."

if [ -n "$PLC_IP" ]; then
    echo "[INFO] Esperando respuesta del PLC en $PLC_IP..."
    until ping -I "$IFACE" -c 1 -W 1 "$PLC_IP" >/dev/null 2>&1; do
        sleep 1
    done
    echo "[OK] PLC responde en $PLC_IP."
    FILTER="src host $PLC_IP"
else
    FILTER=""
fi

{
    echo "Inicio: $(date)"
    echo "Interfaz: $IFACE"
    echo "PLC IP: ${PLC_IP:-no especificada}"
    echo "Filtro tcpdump: ${FILTER:-sin filtro, captura todo en la interfaz}"
    echo ""
} >> "$TEXT_LOG"

echo ""
echo "[INFO] Capturando trafico entrante. Presiona Ctrl+C para detener."
echo "[INFO] Log legible: $TEXT_LOG"
echo "[INFO] Captura completa: $PCAP_LOG"
echo ""

cleanup() {
    if [ -n "$PCAP_PID" ]; then
        kill "$PCAP_PID" 2>/dev/null || true
        wait "$PCAP_PID" 2>/dev/null || true
    fi
    echo ""
    echo "[INFO] Captura detenida: $(date)" | tee -a "$TEXT_LOG"
    echo "[INFO] Archivos generados:"
    echo "       $TEXT_LOG"
    echo "       $PCAP_LOG"
}
trap cleanup EXIT
trap "exit 0" INT TERM

if [ -n "$FILTER" ]; then
    tcpdump -i "$IFACE" -nn -tttt -vvv -s 0 -w "$PCAP_LOG" "$FILTER" &
else
    tcpdump -i "$IFACE" -nn -tttt -vvv -s 0 -w "$PCAP_LOG" &
fi
PCAP_PID=$!

if [ -n "$FILTER" ]; then
    tcpdump -i "$IFACE" -nn -tttt -vvv "$FILTER" | tee -a "$TEXT_LOG"
else
    tcpdump -i "$IFACE" -nn -tttt -vvv | tee -a "$TEXT_LOG"
fi

exit 0
