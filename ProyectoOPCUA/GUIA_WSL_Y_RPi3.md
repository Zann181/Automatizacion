# Guía Técnica: Configuración con WSL para Raspberry Pi 3 Model B

Esta guía te guiará paso a paso para configurar tu entorno de **WSL (Windows Subsystem for Linux)** y adaptar el proyecto **ProyectoOPCUA** para que corra de manera nativa y óptima en una **Raspberry Pi 3 Model B**.

---

## 1. Concepto Fundamental: ¿Por qué no compilar en WSL para la RPi?
Es importante entender la diferencia de arquitecturas:
*   **Tu PC / WSL**: Usa arquitectura **x86_64** (procesadores Intel/AMD).
*   **Raspberry Pi 3 Model B**: Usa un procesador **ARM Cortex-A53** (arquitectura de 32 bits `armhf` o de 64 bits `arm64`).

Si ejecutas `make` directamente en WSL, obtendrás un archivo binario ejecutable para PC. Si intentas llevar ese archivo a la Raspberry Pi, saldrá el error:
> `bash: ./bin/clasificador_plc: cannot execute binary file: Exec format error`

### El Flujo Correcto es:
Usar **WSL** como máquina puente con internet para descargar las dependencias de ARM, empaquetar el proyecto, y luego realizar la **compilación final de forma nativa en la propia Raspberry Pi 3**.

---

## 2. Preparación del Entorno de WSL en Windows

### Paso 2.1: Reparación e Instalación de WSL Ubuntu
Si tu distribución estaba corrupta, realiza estos pasos en tu consola PowerShell de Windows:

1.  Desregistrar la versión dañada:
    ```powershell
    wsl --unregister Ubuntu
    ```
2.  Instalar una versión limpia de Ubuntu (ejecutar en PowerShell):
    ```powershell
    wsl --install -d Ubuntu
    ```
    *Nota: Si se detiene o te pide reiniciar el PC, hazlo y vuelve a abrir la terminal de Ubuntu.*
3.  Una vez que se abra la consola de Ubuntu, crea tu usuario y contraseña.

### Paso 2.2: Habilitar Multiarquitectura en WSL para descargar paquetes ARM
Para que tu WSL (x86_64) pueda buscar y descargar paquetes específicos para la Raspberry Pi (ARM), debes habilitar la arquitectura extranjera:

1.  Abre la terminal de **WSL Ubuntu** y ejecuta:
    ```bash
    # Agregar la arquitectura de la RPi 3 (32-bit armhf o 64-bit arm64)
    sudo dpkg --add-architecture armhf
    ```
2.  Actualiza las listas de paquetes:
    ```bash
    sudo apt-get update
    ```

---

## 3. Preparación de Paquetes Offline desde WSL

Si tu Raspberry Pi 3 no va a tener conexión a internet en la fábrica, puedes descargar todas las librerías necesarias directamente desde WSL y luego transferirlas.

### Paso 3.1: Descargar Dependencias para ARM
En la consola de WSL, navega a la carpeta de tu proyecto (que Windows monta automáticamente en `/mnt/c/`):

```bash
cd /mnt/c/Users/Motaz/Desktop/Unal/Automatizacion/ProyectoOPCUA
```

Ejecuta el script de descarga especificando la arquitectura de la Raspberry Pi:
```bash
# Descarga todas las dependencias (.deb) para ARM de 32-bits (RPi 3)
sudo ./scripts/instalar_sin_internet.sh --descargar
```
*Esto creará la carpeta `paquetes_offline/` llena con todos los archivos `.deb` de `g++`, `sqlite3`, `libssl-dev`, `libopen62541-dev`, etc., listos para la Raspberry Pi.*

---

## 4. Instalación y Compilación en la Raspberry Pi 3 Model B

### Paso 4.1: Transferir el Proyecto a la Raspberry Pi
Conecta la Raspberry Pi a la misma red local que tu PC (o conéctalas directamente con un cable Ethernet). 
Desde la terminal de tu PC (o WSL), copia toda la carpeta del proyecto a la Raspberry Pi:

```bash
# Reemplaza 'pi' y la IP por el usuario e IP reales de tu RPi 3
scp -r . pi@192.168.10.10:~/ProyectoOPCUA
```
*También puedes simplemente copiar la carpeta del proyecto a una memoria USB en formato FAT32/NTFS y conectarla a la Raspberry Pi.*

### Paso 4.2: Instalación Offline de las Dependencias en la RPi
Inicia sesión en la consola de la Raspberry Pi (físicamente o vía SSH) y ejecuta:

```bash
cd ~/ProyectoOPCUA
# Dar permisos de ejecucion
chmod +x scripts/*.sh

# Instalar todos los paquetes .deb descargados por WSL
./scripts/instalar_sin_internet.sh --instalar
```
*El script instalará automáticamente todas las librerías en el orden correcto y sin pedir internet.*

### Paso 4.3: Compilación Nativa en la RPi
Una vez que las dependencias estén instaladas, compila el código fuente para generar el binario ARM ejecutable:

```bash
# 1. Generar certificados SSL para habilitar la interfaz segura HTTPS
./scripts/generar_certificados.sh

# 2. Compilar el proyecto usando el Makefile oficial
make
```

### Paso 4.4: Ejecución del Programa
Una vez compilado de forma exitosa, enciende el servidor en la Raspberry Pi con:

```bash
./bin/clasificador_plc
```

---

## 5. Método Alternativo y Más Sencillo: Compartir Internet (Ruta Online)
Si prefieres no lidiar con paquetes offline en WSL, puedes conectar la Raspberry Pi por Ethernet directamente al PC y darle internet temporal para instalar todo directamente:

1.  Abre PowerShell en Windows como **Administrador** y ejecuta el script:
    ```powershell
    powershell -ExecutionPolicy Bypass -File C:\Users\Motaz\Desktop\Unal\Automatizacion\ProyectoOPCUA\scripts\compartir_internet_rpi.ps1
    ```
2.  En la Raspberry Pi, ejecuta para obtener IP e Internet:
    ```bash
    sudo dhclient eth0
    ```
3.  Instala y compila todo en un solo comando directo en la RPi:
    ```bash
    sudo apt-get update && make install-deps && ./scripts/generar_certificados.sh && make
    ```
4.  Restaura la IP fija estática para la comunicación industrial con el PLC:
    ```bash
    sudo bash ~/ProyectoOPCUA/scripts/configurar_ethernet.sh
    ```
