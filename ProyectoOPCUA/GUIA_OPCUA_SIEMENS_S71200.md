# Guía de Configuración: Conexión de Raspberry Pi con OPC UA y Siemens S7-1200

Esta guía proporciona la configuración detallada para conectar una **Raspberry Pi 3 Model B** como Cliente OPC UA a un PLC **Siemens S7-1200** actuando como Servidor OPC UA. Incluye el análisis crítico del muestreo, tiempos de ciclo, direccionamiento IP y la configuración paso a paso en **TIA Portal**.

---

## 1. Análisis del Muestreo y Latencia del PLC

Para cumplir con el requerimiento **RNF1 (Presupuesto de Latencia $\le 500\text{ms}$)** y el indicador **PU-02 (Ciclo de red $\Delta t_{red} < 50\text{ms}$)**, debemos optimizar el muestreo a nivel físico, lógico y de red:

```
                      PRESUPUESTO DE LATENCIA (T_total <= 500ms)
┌───────────────────┬───────────────────────────────┬───────────────┬────────────────┐
│  T_stream (Video) │ T_procesamiento_QR (Visión)   │  T_red_OPC    │   T_scan_PLC   │
│    (~33ms/frame)  │        (~100-200ms)           │   (< 50ms)    │    (~5-15ms)   │
└───────────────────┴───────────────────────────────┴───────────────┴────────────────┘
```

### Factores Clave a Tener en Cuenta:

1. **Tiempo de Ciclo del PLC ($T_{scan\_PLC}$)**:
   - Es el tiempo que tarda la CPU en ejecutar el bloque principal (`OB1`). Típicamente oscila entre **2ms y 15ms** en un S7-1200.
   - **Recomendación**: Mantener el código del PLC limpio de bucles infinitos o esperas activas (`delay`). Las temporizaciones de los pistones se deben hacer de forma asíncrona mediante bloques temporizadores (`TON`/`TOF`).

2. **Carga de Comunicación (Communication Load)**:
   - Por defecto, el S7-1200 reserva el **20%** del tiempo de ciclo de la CPU para tareas de comunicación (incluido el servidor OPC UA).
   - Si la latencia de actualización es alta, este valor puede incrementarse en TIA Portal (hasta un **30% - 50%**) en: `Propiedades de la CPU -> Ciclo (Cycle) -> Carga de comunicación (Communication load)`. *Nota: Aumentar esto incrementará ligeramente el tiempo de ciclo de la CPU.*

3. **Intervalo de Muestreo de OPC UA (Sampling Interval)**:
   - Define la frecuencia con la que el servidor OPC UA lee el valor de la memoria física del PLC. En S7-1200, el intervalo mínimo recomendado/soportado suele ser **50ms** o **100ms** (según el firmware).
   - **Recomendación**: Configurar el muestreo de las variables críticas (`Motor_State`, `Piston1`, `Piston2`) en el PLC a un mínimo de **50ms**.

4. **Intervalo de Publicación de OPC UA (Publishing Interval)**:
   - Define con qué frecuencia el servidor envía los datos cambiados al cliente (Raspberry Pi).
   - En nuestro código (`OPCManager.cpp`), se configura mediante `requestedPublishingInterval = var.scan_rate_ms`. Este valor debe establecerse en **50ms** para las variables de control y **100-250ms** para monitoreo analógico (`Motor_Speed`).

---

## 2. Configuración Física y de Red

Ambos dispositivos deben pertenecer a la misma subred física y lógica.

### Direccionamiento IP
* **Subred**: `192.168.0.x`
* **Máscara de Subred**: `255.255.255.0`
* **IP del PLC S7-1200**: `192.168.0.1`
* **IP de la Raspberry Pi**: `192.168.0.10`

### Conexión de Hardware
- **Directa**: Un cable Ethernet RJ45 directo entre el puerto `X1` del S7-1200 y el puerto Ethernet de la Raspberry Pi. (Las tarjetas modernas de ambos dispositivos admiten **Auto-MDIX**, por lo que no requiere cable cruzado obligatoriamente).
- **Industrial (Switch)**: Recomendada si se requiere conectar simultáneamente la PC de desarrollo, la HMI, la RPi y el PLC.

---

## 3. Configuración del PLC en TIA Portal (Siemens S7-1200)

Sigue estos pasos detallados en **TIA Portal (v16 o superior)**:

### Paso 3.1: Configurar Licencia de Runtime y Habilitar el Servidor OPC UA
1. **Activar la Licencia de Runtime**:
   - En TIA Portal, abre la **Configuración de dispositivos (Device configuration)**.
   - Selecciona la CPU S7-1200 y abre sus **Propiedades** (doble clic o clic derecho -> Propiedades).
   - En la pestaña General, navega en el árbol de propiedades a: `Licencias de Runtime (Runtime licenses) -> OPC UA`.
   - En la sección **Licencia requerida (Required license)**, abre el menú desplegable y selecciona **SIMATIC OPC UA S7-1200 Basic**.
   - *Nota: Si no seleccionas esta licencia, la CPU no activará el servidor OPC UA al cargar el proyecto o TIA Portal arrojará un error de compilación.*
2. **Habilitar el Servidor OPC UA**:
   - En la misma ventana de Propiedades, ve a: `OPC UA -> Servidor (Server)`.
   - Marca la casilla **Activar servidor OPC UA (Activate OPC UA server)**.
   - Verifica el puerto de escucha predeterminado, que para el S7-1200 es el **`4840`**.
   - **Endpoint URL**: `opc.tcp://192.168.0.1:4840`

### Paso 3.2: Configuración de Seguridad (Security)
Para la fase de pruebas y puesta en marcha:
1. Ve a `OPC UA -> Servidor -> Seguridad (Security)`.
2. En **Políticas de seguridad (Security policies)**, activa la opción **Sin seguridad (No security / None)**.
3. En **Autenticación de usuario (User authentication)**, activa **Acceso anónimo (Anonymous access)**.
4. *Nota para producción*: Se recomienda desactivar "None" y configurar certificados SSL y usuario/contraseña. El script `scripts/generar_certificados.sh` del proyecto genera los certificados necesarios para el lado de la Raspberry Pi.

### Paso 3.3: Configurar las Variables y Acceso a Bloques (DB)
El cliente OPC UA del proyecto busca variables con nombres específicos. 

1. **Crear Bloque de Datos (DB)**: Crea un DB global (por ejemplo, `DB_OPCUA`).
2. **Propiedades del DB**: Haz clic derecho sobre el DB creado, selecciona **Propiedades (Properties)** y asegúrate de **desmarcar** la opción **Acceso optimizado al bloque (Optimized block access)** si deseas usar direccionamiento absoluto clásico, **O** déjalo marcado pero asegúrate de que la columna **"Accesible desde OPC UA"** esté activa para todas las variables del bloque.
3. **Declarar las Variables**:
   Declara las siguientes variables exactamente como se indica en la matriz del proyecto:

   | Nombre de Variable | Tipo de Dato | Dirección / Atributo | Nodo OPC UA (Namespace Estándar)* |
   | :--- | :--- | :--- | :--- |
   | `Motor_State` | `BOOL` | Lectura/Escritura | `ns=3;s="DB_OPCUA"."Motor_State"` |
   | `Motor_Speed` | `REAL` (Float) | Solo Lectura | `ns=3;s="DB_OPCUA"."Motor_Speed"` |
   | `Piston1` | `BOOL` | Lectura/Escritura | `ns=3;s="DB_OPCUA"."Piston1"` |
   | `Piston2` | `BOOL` | Lectura/Escritura | `ns=3;s="DB_OPCUA"."Piston2"` |

   *\*Nota: El Namespace del direccionamiento estándar SIMATIC en S7-1200 es usualmente el índice `3`. Para usar interfaces de servidor dedicadas, ver el siguiente paso.*

4. **Crear la Interfaz del Servidor (Server Interface) [RECOMENDADO]**:
   Para que la comunicación se realice de forma estructurada a través de una Interfaz de Servidor OPC UA dedicada (evitando exponer todo el bloque de datos y logrando NodeIDs más simples):
   - En el árbol del proyecto de TIA Portal, ve a `Comunicación OPC UA (OPC UA Communication) -> Interfaces de servidor (Server interfaces)`.
   - Haz doble clic en **Agregar nueva interfaz de servidor (Add new server interface)** y asígnale un nombre descriptivo, por ejemplo: `InterfacesOPC`.
   - En la ventana que se abre, verás dos paneles: a la izquierda, la estructura de tu PLC (bloques de datos, tablas de variables), y a la derecha, la interfaz de servidor vacía.
   - Selecciona las variables (`Motor_State`, `Motor_Speed`, `Piston1`, `Piston2`) desde tu DB en el panel izquierdo y **arrástralas** hacia la sección derecha de la interfaz de servidor.
   - Al hacer esto, las variables se publican con identificadores limpios en un espacio de nombres dedicado:
     
     | Variable | Tipo de Dato | Dirección en la Interfaz | Nodo OPC UA (Server Interface)* |
     | :--- | :--- | :--- | :--- |
     | `Motor_State` | `BOOL` | Mapeado directo | `ns=4;s="Motor_State"` (o `ns=4;s="InterfacesOPC"."Motor_State"`) |
     | `Motor_Speed` | `REAL` | Mapeado directo | `ns=4;s="Motor_Speed"` (o `ns=4;s="InterfacesOPC"."Motor_Speed"`) |
     | `Piston1` | `BOOL` | Mapeado directo | `ns=4;s="Piston1"` (o `ns=4;s="InterfacesOPC"."Piston1"`) |
     | `Piston2` | `BOOL` | Mapeado directo | `ns=4;s="Piston2"` (o `ns=4;s="InterfacesOPC"."Piston2"`) |

   > [!IMPORTANT]
   > **Namespace Index e Identificadores (NodeIDs):**
   > - **Namespace Index (Índice)**: En TIA Portal con S7-1200, la interfaz de servidor personalizada se publica usualmente bajo el **Namespace Index 4** (o 3 si se deshabilita la interfaz estándar SIMATIC). Puedes consultar la URI de la interfaz en sus propiedades (ej. `http://www.siemens.com/simatic-s7-1200/opc-ua/server-interfaces/InterfacesOPC`).
   > - **Sincronización en la App**: Debes asegurarte de que el Namespace Index y los NodeIDs configurados en tu base de datos (`config_plc.db` o la tabla `opc_variables`) coincidan exactamente con lo que ves en TIA Portal (ej. cambiar el Namespace Index de `2` a `4` o `3` según corresponda).

5. **Compilar y Cargar**: Compila la configuración del hardware y del software y cárgala al PLC S7-1200.

---

## 4. Configuración del Sistema en la Raspberry Pi 3

### Paso 4.1: Asignar IP Estática a la Interfaz de Red
Ejecuta el script incluido en el proyecto para configurar la IP de la Raspberry Pi de forma automática y estática:
```bash
cd ~/ProyectoOPCUA
sudo chmod +x scripts/*.sh
sudo bash scripts/configurar_ethernet.sh
```
*Esto configurará la interfaz de cable `eth0` a `192.168.0.10/24`.*

### Paso 4.2: Instalación de Dependencias y Compilación
Si la Raspberry Pi tiene acceso a internet:
```bash
sudo apt-get update
sudo apt-get install -y build-essential libsqlite3-dev sqlite3 libopen62541-dev openssl tcpdump
./scripts/generar_certificados.sh
make
```

Si la Raspberry Pi está en un entorno industrial **sin internet**, puedes descargar las dependencias desde tu computadora (WSL) y luego instalarlas localmente:
1. **En WSL**:
   ```bash
   cd /mnt/c/Users/Motaz/Desktop/Unal/Automatizacion/ProyectoOPCUA
   sudo ./scripts/instalar_sin_internet.sh --descargar
   ```
2. **Transferir a RPi** (Vía USB o SCP) e instalar:
   ```bash
   cd ~/ProyectoOPCUA
   sudo ./scripts/instalar_sin_internet.sh --instalar
   ./scripts/generar_certificados.sh
   make
   ```

---

## 5. Diagnóstico y Pruebas de Conexión

### Diagnóstico de Red (Ping)
Desde la terminal de la Raspberry Pi, comprueba que la tarjeta de red del PLC responde:
```bash
ping -c 4 192.168.0.1
```

### Diagnóstico del Cliente (UaExpert)
Antes de iniciar tu aplicación, se recomienda validar la configuración del servidor del PLC utilizando **UaExpert** (u otro explorador OPC UA cliente) desde una PC de desarrollo conectada a la misma red:
1. Agrega el servidor usando el URL del Endpoint: `opc.tcp://192.168.0.1:4840`.
2. Verifica que las políticas de seguridad muestren "None" y conecta sin credenciales (Anonymous).
3. Busca en la carpeta `Objects` las variables expuestas en el Namespace (revisa si es Namespace Index 3 o 4 según tu interfaz de servidor en TIA Portal).
4. Intenta cambiar el valor de `Motor_State` y verifica que se refleje físicamente en el PLC.

### Ejecución de la Aplicación en la Raspberry Pi
Una vez verificado el enlace, enciende el software clasificador del proyecto:
```bash
./bin/clasificador_plc
```
Este programa se conectará al Endpoint `opc.tcp://192.168.0.1:4840` y gestionará la lectura y escritura en tiempo real de forma sincronizada con el procesamiento de visión por computadora.
