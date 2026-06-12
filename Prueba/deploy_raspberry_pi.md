# Guía de Despliegue en Raspberry Pi (Sin Internet / Offline)

Esta guía detalla el procedimiento paso a paso para transferir e instalar el sistema de clasificación QR en la Raspberry Pi con dirección IP `192.168.0.13` (usuario `alex`) sin requerir conexión a Internet en la Raspberry Pi.

---

## 📋 Requisitos Previos

1. **PC con Internet (Windows):** Se utilizará para descargar los archivos de instalación (ruedas/wheels `.whl`) de las dependencias de Python y luego transferirlos a la Raspberry Pi.
2. **Raspberry Pi (Sin Internet):** Debe tener instalado Python 3 y la herramienta de entornos virtuales `python3-venv` (por defecto incluida en la mayoría de distros).

---

## 🛠️ Paso 1: Obtener Datos de la Raspberry Pi

Conéctate a la Raspberry Pi mediante SSH para verificar la versión exacta de Python y la arquitectura del procesador:

```bash
# Conectarse a la Raspberry Pi
ssh alex@192.168.0.13

# 1. Consultar versión de Python (ej. 3.9, 3.11, etc.)
python3 --version

# 2. Consultar la arquitectura (ej. aarch64 o armv7l)
uname -m

# Cierra la sesión SSH para volver a tu PC
exit
```

---

## 💾 Paso 2: Descargar Dependencias Offline (En la PC con Internet)

Ejecuta el script automatizado [download_wheels.py](file:///c:/Users/Motaz/Desktop/Unal/Automatizacion/Prueba/download_wheels.py) que se encuentra en la carpeta del proyecto. Este script descargará los archivos binarios `.whl` (wheels) específicos para Linux ARM:

1. Abre una terminal de **PowerShell** en la carpeta del proyecto.
2. Corre el script:
   ```powershell
   venv\Scripts\python.exe download_wheels.py
   ```
3. Introduce la versión de Python de tu Raspberry Pi (por defecto `3.9`) y la arquitectura (por defecto `aarch64` si es un sistema de 64 bits o `armv7l` si es de 32 bits).
4. El script creará una carpeta llamada `wheels/` en la raíz del proyecto y descargará allí todos los paquetes requeridos por [requirements.txt](file:///c:/Users/Motaz/Desktop/Unal/Automatizacion/Prueba/requirements.txt).

---

## 🚀 Paso 3: Transferir Archivos a la Raspberry Pi

Usa `scp` (Secure Copy Protocol, integrado en Windows) para copiar todo el proyecto, incluida la carpeta `wheels/` recién creada, a la Raspberry Pi:

```powershell
# Abre una consola de PowerShell en Windows y ejecuta:
# (Este comando copia todo el proyecto a la carpeta /home/alex/clasificador en la Pi)
scp -r c:\Users\Motaz\Desktop\Unal\Automatizacion\Prueba alex@192.168.0.13:/home/alex/clasificador
```

*Nota: Durante el proceso se te solicitará la contraseña del usuario `alex` de la Raspberry Pi.*

---

## 📦 Paso 4: Instalación Offline (En la Raspberry Pi)

Vuelve a conectarte por SSH a la Raspberry Pi para instalar las dependencias localmente sin usar Internet:

```bash
# 1. Conectarse por SSH
ssh alex@192.168.0.13

# 2. Entrar a la carpeta del proyecto
cd /home/alex/clasificador

# 3. Crear un entorno virtual de Python limpio
python3 -m venv venv

# 4. Activar el entorno virtual
source venv/bin/activate

# 5. Instalar las dependencias usando la carpeta local 'wheels/'
pip install --no-index --find-links=wheels/ -r requirements.txt
```

---

## ⚙️ Paso 5: Ejecutar el Servidor y Configurar Servicio de Inicio

### Ejecución Directa de Prueba:
```bash
python3 "servidor(new).py"
```
El servidor arrancará en `https://0.0.0.0:8000`. Recuerda aceptar la advertencia del certificado de seguridad en tu navegador/móvil al ingresar por primera vez.

### Configurar como Servicio del Sistema (Recomendado):
Para que el clasificador se inicie automáticamente cada vez que se encienda la Raspberry Pi, crea un servicio `systemd`:

1. Crea el archivo de servicio:
   ```bash
   sudo nano /etc/systemd/system/clasificador.service
   ```
2. Pega el siguiente contenido (ajustando las rutas si es necesario):
   ```ini
   [Unit]
   Description=Servidor Clasificador Industrial QR y PLC
   After=network.target

   [Service]
   Type=simple
   User=alex
   WorkingDirectory=/home/alex/clasificador
   ExecStart=/home/alex/clasificador/venv/bin/python3 "servidor(new).py"
   Restart=always
   RestartSec=5

   [Install]
   WantedBy=multi-user.target
   ```
3. Guarda el archivo (`Ctrl+O`, `Enter`) y sal (`Ctrl+X`).
4. Habilita e inicia el servicio:
   ```bash
   # Recargar systemd
   sudo systemctl daemon-reload

   # Habilitar para arranque automático
   sudo systemctl enable clasificador.service

   # Iniciar el servicio ahora mismo
   sudo systemctl start clasificador.service

   # Ver estado de ejecución actual
   sudo systemctl status clasificador.service
   ```

Ahora el servidor estará activo en segundo plano en la Raspberry Pi de forma indefinida y reactivo ante reinicios o cortes de energía.

---

## ⚠️ Solución de Problemas: Error con `cffi` o `cryptography`

`cffi` y `cryptography` son dependencias que requieren compilación en C y enlazan con librerías del sistema como `libffi` y `libssl`. En la Raspberry Pi (especialmente sin internet), esto suele dar error como `ffi.h: No such file or directory` o problemas con `_cffi_backend`.

Elige **una** de las siguientes tres opciones para solucionarlo:

### Opción A: Utilizar paquetes del sistema precompilados (Recomendada y más fácil)

Dado que Raspberry Pi OS (Debian) ya incluye paquetes binarios compilados y listos para su procesador, puedes instalarlos a nivel de sistema y permitir que tu entorno virtual los use:

1. **Instala las dependencias en la Raspberry Pi** (requiere internet temporal en la Pi, por ejemplo, compartiendo el internet de tu PC o por Wi-Fi):
   ```bash
   sudo apt-get update
   sudo apt-get install -y python3-cffi python3-cryptography
   ```
2. **Recrea tu entorno virtual** permitiendo el acceso a los paquetes globales del sistema:
   ```bash
   # Entra a la carpeta del proyecto
   cd /home/alex/clasificador
   
   # Elimina el entorno virtual anterior si existía
   rm -rf venv
   
   # Crea el nuevo entorno virtual con el flag --system-site-packages
   python3 -m venv --system-site-packages venv
   
   # Actívalo
   source venv/bin/activate
   
   # Instala el resto de dependencias desde tu carpeta wheels local (offline)
   pip install --no-index --find-links=wheels/ -r requirements.txt
   ```
   *¿Por qué funciona?* Al activar `--system-site-packages`, `pip` detecta que `cffi` y `cryptography` ya están instalados de forma segura a nivel de sistema por el gestor `apt` y no intentará compilarlos ni descargarlos offline, instalando solo los paquetes restantes (FastAPI, uvicorn, asyncua, etc.) desde tu carpeta `wheels/`.

---

### Opción B: Descargar la rueda (wheel) correcta desde piwheels.org (100% Offline)

Si la Raspberry Pi no tiene conexión a internet bajo ningún concepto, puedes descargar el archivo `.whl` compilado para Raspberry Pi en tu PC con internet y transferirlo:

1. **Obtén las ruedas precompiladas de Piwheels:**
   * Abre tu navegador en la PC y entra a:
     * [piwheels.org/project/cffi](https://www.piwheels.org/project/cffi/)
     * [piwheels.org/project/cryptography](https://www.piwheels.org/project/cryptography/)
   * Descarga el archivo `.whl` que coincida exactamente con:
     * La versión de Python de tu Pi (ej. `cp39` para Python 3.9).
     * La arquitectura de tu sistema (ej. `armv7l` para sistemas de 32 bits, o `aarch64` para 64 bits).
2. **Coloca estos archivos en la carpeta `wheels/`** de tu PC.
3. Vuelve a ejecutar la transferencia `scp` hacia la Raspberry Pi para actualizar la carpeta `wheels/` en la Pi.
4. Ejecuta el comando de instalación en la Pi:
   ```bash
   source venv/bin/activate
   pip install --no-index --find-links=wheels/ -r requirements.txt
   ```

---

### Opción C: Instalar las librerías de desarrollo C en la Raspberry Pi (Para compilar desde código fuente)

Si deseas que `pip` pueda compilar `cffi` y `cryptography` directamente en la Pi, debes instalar los compiladores y cabeceras de desarrollo necesarios (requiere internet temporal en la Pi):

```bash
sudo apt-get update
sudo apt-get install -y build-essential libffi-dev python3-dev libssl-dev
```

Una vez instalados estos paquetes de desarrollo del sistema, la instalación offline normal o la compilación mediante `pip` de `cffi` y `cryptography` funcionará sin errores.

