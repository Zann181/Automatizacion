# Guía de Conexión Industrial: PLC <-> Raspberry Pi / PC por Puerto Ethernet

Esta guía técnica explica paso a paso cómo realizar la conexión física, la configuración de red y la comunicación OPC-UA entre tu **PLC industrial** y la **Raspberry Pi 3 Model B** (o tu **PC con Windows** para desarrollo).

---

## 1. Conexión Física de Hardware

Existen dos maneras de conectar físicamente el PLC al PC o a la Raspberry Pi:

### Conexión Directa (Recomendado para pruebas)
Consiste en conectar un único cable de red RJ45 directamente desde el puerto Ethernet del PLC al puerto Ethernet del PC o Raspberry Pi.
> [!NOTE]
> Las tarjetas de red modernas soportan **Auto-MDIX**, lo que significa que puedes usar un cable de red estándar (directo) o cruzado de manera indiferente; la propia tarjeta cruzará las líneas de transmisión y recepción de forma automática.

```
┌──────────────┐                  Cable Ethernet RJ45                  ┌─────────────────────┐
│   PLC Real   │=======================================================│   PC / Raspberry    │
└──────────────┘                                                       └─────────────────────┘
```

### Conexión a través de un Switch (Recomendado para campo)
Si necesitas conectar múltiples dispositivos (ej. tu PC, la Raspberry Pi, el PLC, y una pantalla HMI), utiliza un Switch Ethernet industrial. Conecta cada dispositivo a un puerto del Switch con cables RJ45 estándar.

```
┌──────────────┐        ┌──────────────┐        ┌─────────────────────┐
│   PLC Real   │        │ Pantalla HMI │        │   PC / Raspberry    │
└──────┬───────┘        └──────┬───────┘        └──────────┬──────────┘
       │                       │                           │
       └──────────────┐        │        ┌──────────────────┘
                      ▼        ▼        ▼
                   ┌───────────────────────┐
                   │    Switch Ethernet    │
                   └───────────────────────┘
```

---

## 2. Configuración de Red (Direccionamiento IP)

Para que el programa (Cliente OPC-UA) pueda comunicarse con el PLC, ambos dispositivos **deben estar configurados en la misma subred de red**. En este proyecto, los valores predeterminados de la base de datos y scripts son:

*   **Subred**: `192.168.0.x`
*   **Máscara de Subred**: `255.255.255.0` (o `/24` en notación CIDR)

---

### Paso 2.1: Configuración en el PLC
Configura tu PLC (utilizando TIA Portal para Siemens, TwinCAT para Beckhoff, etc.) con una IP estática:

*   **Dirección IP del PLC**: `192.168.0.1`
*   **Máscara de Subred**: `255.255.255.0`
*   **Puerta de enlace (Gateway)**: Dejar en blanco o `0.0.0.0`

---

### Paso 2.2: Configuración en la Raspberry Pi 3
En la Raspberry Pi, la IP estática se configura automáticamente ejecutando el script del proyecto. 

1.  Abre la terminal en la Raspberry Pi y navega al proyecto:
    ```bash
    cd ~/ProyectoOPCUA
    ```
2.  Ejecuta el script de red:
    ```bash
    sudo bash scripts/configurar_ethernet.sh
    ```
    *Este script detecta si usas NetworkManager (`nmcli`) o el antiguo `dhcpcd` y configurará tu puerto `eth0` con:*
    *   **Dirección IP de la RPi**: `192.168.0.10`
    *   **Máscara de Subred**: `255.255.255.0`

---

### Paso 2.3: Configuración en tu PC con Windows (para Desarrollo/Simulación)
Si deseas correr la interfaz y el simulador en tu computadora Windows directamente:

1.  Presiona las teclas `Win + R`, escribe `ncpa.cpl` y dale Enter (abre las Conexiones de Red).
2.  Haz clic derecho sobre tu adaptador de red **Ethernet** y selecciona **Propiedades**.
3.  Haz doble clic en **Habilitar el protocolo de Internet versión 4 (TCP/IPv4)**.
4.  Selecciona **Usar la siguiente dirección IP** y rellena:
    *   **Dirección IP**: `192.168.0.10` (o cualquiera en el rango `0.2` a `0.254` excepto la `0.1` del PLC)
    *   **Máscara de Subred**: `255.255.255.0`
    *   **Puerta de enlace**: Dejar vacío.
5.  Acepta y cierra.

---

## 3. Configuración del Servidor OPC-UA en el PLC

El programa actúa como un **Cliente OPC-UA** que busca leer y escribir variables específicas. Debes activar y configurar el servidor OPC-UA en tu PLC:

1.  **Activar Licencia**: En TIA Portal, ve a `Licencias de Runtime -> OPC UA -> Licencia requerida` de la CPU y selecciona **SIMATIC OPC UA S7-1200 Basic**.
2.  **Activar Servidor**: En la configuración de tu PLC, busca la sección "OPC UA" y marca la casilla **Activar servidor OPC UA**.
3.  **Configurar Puerto**: El puerto configurado por defecto es el `4840`. Asegúrate de que el servidor escuche en ese puerto o edítalo en el PLC.
    *   **Endpoint URL del PLC**: `opc.tcp://192.168.0.1:4840`
3.  **Seguridad (Fase de Pruebas)**:
    *   Activa la política de seguridad **None** (Sin seguridad) y el modo de autenticación **Anónimo (Anonymous)**.
    *   *Nota: Una vez comprobada la conexión, se recomienda configurar seguridad mediante certificados SSL generados con `./scripts/generar_certificados.sh`.*
4.  **Crear y Exponer las Variables (Tags)**:
    Crea las siguientes variables exactamente con estos nombres y tipos de datos en la tabla de variables del PLC, y asegúrate de exponerlas al servidor OPC-UA bajo el **Namespace Index 2**:

| Nombre de Variable | Tipo de Dato | Acceso | NodeId (en Namespace 2) | Descripción |
| :--- | :--- | :--- | :--- | :--- |
| **`Motor_State`** | Boolean (BOOL) | Lectura/Escritura | `ns=2;s=Motor_State` | Estado del motor de la banda transportadora (1=ON, 0=OFF). |
| **`Motor_Speed`** | Real / Float (REAL) | Solo Lectura | `ns=2;s=Motor_Speed` | Velocidad real del motor en RPM para el panel de KPIs. |
| **`Piston1`** | Boolean (BOOL) | Lectura/Escritura | `ns=2;s=Piston1` | Actuador del primer pistón selector (Categoría 1). |
| **`Piston2`** | Boolean (BOOL) | Lectura/Escritura | `ns=2;s=Piston2` | Actuador del segundo pistón selector (Categoría 2). |

---

## 4. Verificación de Conexión y Diagnóstico

### Paso 4.1: Prueba de Conectividad de Red (Ping)
Antes de abrir el programa, abre la consola en la Raspberry Pi o Windows y ejecuta:
```bash
ping 192.168.0.1
```
*   **Si responde exitosamente**: El cable y la configuración IP son correctos.
*   **Si da "Timeout" o "Host inaccesible"**: 
    *   Verifica que el cable de red esté bien conectado (el puerto físico Ethernet debe encender luces LED verde y naranja).
    *   Desactiva temporalmente el Firewall de Windows si estás haciendo la prueba desde tu PC.

### Paso 4.2: Prueba de Comunicación OPC-UA
1.  Se recomienda descargar una herramienta externa gratuita en tu PC como **UaExpert** (de Unified Automation).
2.  Añade el servidor conectándote a `opc.tcp://192.168.0.1:4840`.
3.  Verifica que puedas ver el árbol de nodos, arrastrar `Motor_Speed` y ver su valor en vivo, y encender/apagar `Motor_State` de forma manual.
4.  Una vez verificado en UaExpert, arranca tu programa (`./bin/clasificador_plc` en Raspberry o `python run_windows.py` en PC) y este se enlazará automáticamente al PLC industrial.
