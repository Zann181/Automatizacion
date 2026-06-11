#!/bin/bash
# ============================================================
# actualizar_rpi.sh  —  Actualizar configuracion OPC en la RPi
#
# Este script:
#   1. Fuerza la configuracion correcta del PLC en la base de datos
#   2. Copia los archivos web actualizados (main.js, index.html)
#   3. Recompila el binario si es necesario
#   4. Reinicia el servicio
#
# Uso DESDE LA RASPBERRY PI (ejecutar en el directorio del proyecto):
#   chmod +x scripts/actualizar_rpi.sh
#   sudo bash scripts/actualizar_rpi.sh
#
# O desde Windows con SCP + SSH:
#   scp -r web/ pi@<IP_RPi>:~/ProyectoOPCUA/web/
#   ssh pi@<IP_RPi> "cd ~/ProyectoOPCUA && sudo bash scripts/actualizar_rpi.sh"
# ============================================================

set -e

PLC_IP="192.168.0.1"
PLC_PORT=4840
PLC_ENDPOINT="opc.tcp://192.168.0.1:4840"
DB_PATH="./config_plc.db"
SERVICE_NAME="clasificador_plc"
BINARY="./bin/clasificador_plc"

echo ""
echo "=============================================="
echo "  Actualizacion del Sistema OPC-UA"
echo "  PLC IP    : $PLC_IP"
echo "  Puerto    : $PLC_PORT"
echo "  Endpoint  : $PLC_ENDPOINT"
echo "=============================================="
echo ""

# ---- 1. Verificar que sqlite3 este instalado ----
if ! command -v sqlite3 &>/dev/null; then
    echo "[ERROR] sqlite3 no esta instalado. Instalando..."
    sudo apt-get install -y sqlite3
fi

# ---- 2. Actualizar la base de datos ----
if [ -f "$DB_PATH" ]; then
    echo "[DB] Actualizando config_opc en $DB_PATH..."
    sqlite3 "$DB_PATH" \
        "UPDATE config_opc SET ip='$PLC_IP', port=$PLC_PORT, endpoint='$PLC_ENDPOINT' WHERE id=1;"

    # Verificar el resultado
    RESULT=$(sqlite3 "$DB_PATH" "SELECT ip, port, endpoint FROM config_opc WHERE id=1;")
    echo "[DB] Configuracion actual: $RESULT"
    echo "[DB] ✓ Base de datos actualizada."
else
    echo "[DB] ADVERTENCIA: No se encontro $DB_PATH."
    echo "[DB] La DB se creara con los valores correctos al iniciar el servicio."
fi

# ---- 3. Verificar que los archivos web esten actualizados ----
echo ""
echo "[Web] Verificando archivos web..."
if [ -f "./web/index.html" ]; then
    echo "[Web] ✓ index.html encontrado."
else
    echo "[Web] ERROR: No se encontro web/index.html"
    exit 1
fi

if [ -f "./web/js/main.js" ]; then
    echo "[Web] ✓ main.js encontrado."
else
    echo "[Web] ERROR: No se encontro web/js/main.js"
    exit 1
fi

# ---- 4. Recompilar si el binario no existe o el Makefile lo pide ----
echo ""
if [ ! -f "$BINARY" ]; then
    echo "[Build] Binario no encontrado. Compilando..."
    make USE_SSL=1
    echo "[Build] ✓ Compilacion exitosa."
else
    echo "[Build] Binario existente. Para recompilar: make clean && make USE_SSL=1"
fi

# ---- 5. Reiniciar el servicio ----
echo ""
echo "[Service] Buscando proceso activo..."
PIDS=$(pgrep -f "clasificador_plc" 2>/dev/null || true)

if [ -n "$PIDS" ]; then
    echo "[Service] Deteniendo proceso(s): $PIDS"
    kill $PIDS 2>/dev/null || true
    sleep 2
    echo "[Service] ✓ Proceso detenido."
else
    echo "[Service] No habia proceso activo."
fi

# Reiniciar si hay un servicio systemd
if systemctl is-active --quiet "$SERVICE_NAME" 2>/dev/null; then
    echo "[Service] Reiniciando servicio systemd: $SERVICE_NAME"
    sudo systemctl restart "$SERVICE_NAME"
    echo "[Service] ✓ Servicio reiniciado."
else
    echo ""
    echo "[Service] Para iniciar manualmente:"
    echo "   cd $(pwd) && sudo $BINARY"
    echo ""
    echo "[Service] Para ejecutar en background:"
    echo "   sudo nohup $BINARY > /var/log/clasificador_plc.log 2>&1 &"
fi

echo ""
echo "=============================================="
echo "  ✓ Actualizacion completada"
echo "  PLC configurado en: $PLC_ENDPOINT"
echo "  Dashboard en: http://$(hostname -I | awk '{print $1}'):8080"
echo "=============================================="
echo ""
