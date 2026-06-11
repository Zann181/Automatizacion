# Raspberry Pi 2 sin WiFi - Log PLC por Ethernet

Esta carpeta es para una Raspberry Pi 2 conectada directamente al PLC por cable Ethernet, sin usar WiFi.

## Archivos

- `leer_log_plc.sh`: detecta conexion Ethernet y muestra en terminal lo que llega desde el PLC.
- `logs/`: se crea automaticamente cuando ejecutas el script.

## Requisito

El script usa `tcpdump`. Si la Raspberry no lo tiene instalado, instalalo antes:

```bash
sudo apt-get install tcpdump
```

Si la Raspberry no tiene internet, instala `tcpdump` copiando el paquete `.deb` desde otra maquina.

## Uso simple

En la Raspberry, entra a esta carpeta y ejecuta:

```bash
sudo bash leer_log_plc.sh
```

Eso espera hasta que conectes el cable Ethernet en `eth0` y empieza a mostrar el trafico en terminal.

## Uso con IP del PLC

Si sabes la IP del PLC, por ejemplo `192.168.10.11`, ejecuta:

```bash
sudo bash leer_log_plc.sh 192.168.10.11
```

Asi el log queda filtrado solo a lo que llega desde ese PLC.

## Salida

El script genera dos archivos:

- `logs/plc_*.log`: texto visible desde terminal.
- `logs/plc_*.pcap`: captura completa para abrir con Wireshark.

Para detenerlo, presiona `Ctrl+C`.
