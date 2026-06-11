#!/bin/bash
set -x

# 1. Detener el servicio activo
echo "motas177" | sudo -S systemctl stop clasificador_plc || true
echo "motas177" | sudo -S pkill -f clasificador_plc || true

# 2. Borrar la base de datos para forzar la recreación con el formato "Bloque de datos_1" en namespace 3
rm -f /home/alex/ProyectoOPCUA/config_plc.db*

# 3. Compilar de nuevo e iniciar el servicio
cd /home/alex/ProyectoOPCUA
make clean
make USE_SSL=1
echo "motas177" | sudo -S systemctl start clasificador_plc
