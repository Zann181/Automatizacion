# Sistema Industrial: Raspberry Pi (OPC UA + Interfaz Web + Router WiFi)

Este proyecto convierte tu **Raspberry Pi 3 Model B** en una herramienta industrial integral. Se conectará directamente al PLC por Ethernet usando OPC UA, servirá una página web interactiva y, además, **creará su propia red WiFi** para que puedas controlarla de manera inalámbrica sin depender del internet de la fábrica.

## 1. Conectar la Raspberry a tu Red WiFi

Para que cualquier dispositivo (celulares, computadoras) en tu red local pueda ver la interfaz de la Raspberry Pi, primero debemos conectarla al WiFi.

Abre la terminal de la Raspberry Pi (o usa un teclado/monitor conectado a ella) y ejecuta:

```bash
# Ver las redes WiFi disponibles:
nmcli device wifi list

# Conectarte a tu red:
sudo nmcli device wifi connect "NombreDeTuRed" password "TuContraseña"
```

Una vez conectada, averigua qué IP le asignó el router escribiendo:
```bash
hostname -I
```
*Anota la primera IP que te salga (ej. 192.168.1.8). Esa será tu IP de acceso.*

## 2. Requisitos de Instalación

*(Nota: Como ahora la Raspberry emite su propio WiFi, no tendrá internet temporalmente. Para instalar lo siguiente, conéctale un cable Ethernet que tenga internet, o desactiva la red temporalmente si estás por WiFi).*

Abre la terminal en tu Raspberry Pi y ejecuta:

```bash
# Actualizar repositorios
sudo apt-get update

# Instalar herramientas de compilación
sudo apt-get install build-essential g++ wget

# Instalar SQLite3
sudo apt-get install libsqlite3-dev sqlite3

# Instalar open62541 (librería OPC UA)
sudo apt-get install libopen62541-dev

# Opcional: capturar/loguear trafico Ethernet del PLC
sudo apt-get install tcpdump
```

## 3. Compilación

Navega a la carpeta del proyecto y ejecuta el archivo Makefile:

```bash
cd /ruta/a/ProyectoOPCUA
make
```

*(El Makefile descargará automáticamente la librería `httplib.h` y creará el ejecutable).*

## 4. Ejecución y Control

1. **Encender el Servidor:**
   Asegúrate de que el PLC esté conectado por cable Ethernet a la Raspberry Pi.
   Inicia el programa con:
   ```bash
   ./bin/cliente_opcua
   ```

4. **Acceder a la Interfaz Web:**
   - Asegúrate de que tu celular o laptop esté conectada al mismo WiFi que la Raspberry.
   - Abre tu navegador y entra a la IP que anotaste en el Paso 1, agregando `:8080` al final. Ejemplo:
     `http://192.168.1.8:8080`
   
3. **Controlar el PLC:**
   En la pantalla de tu celular/laptop, escribe la IP local de tu PLC (ej. `192.168.0.1`), dale a **Conectar** y empieza a leer y escribir variables industriales. Todo quedará grabado en la base de datos interna `datos_plc.db`.

## 5. Log de Conexion Ethernet del PLC

Para detectar cuando el PLC se conecta por Ethernet y guardar todo lo que llega por la interfaz `eth0`, ejecuta en la Raspberry:

```bash
sudo bash scripts/log_plc_ethernet.sh
```

Si conoces la IP del PLC, pasala como parametro para guardar solo lo que llega desde ese equipo:

```bash
sudo bash scripts/log_plc_ethernet.sh 192.168.0.1
```

El script espera hasta que haya enlace Ethernet, verifica la IP del PLC si la pasaste, y genera archivos en `logs/`:

- `plc_ethernet_*.log`: resumen legible en texto.
- `plc_ethernet_*.pcap`: captura completa para abrir en Wireshark o revisar con `tcpdump`.

## 6. Carpeta Simple para Raspberry Pi 2 sin WiFi

Si solo necesitas leer logs del PLC desde la terminal de una Raspberry Pi 2 sin WiFi, usa la carpeta:

```bash
raspberry_pi_2_sin_wifi/
```

Dentro esta el script simple:

```bash
sudo bash leer_log_plc.sh
```
