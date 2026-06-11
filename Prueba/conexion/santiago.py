import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from asyncua import Client, ua

# ---------------------------------------------------------
# CONFIGURACIÓN DEL PLC
# ---------------------------------------------------------
URL = "opc.tcp://192.168.0.1:4840"

# Instanciamos el cliente OPC UA de forma global para mantener la conexión viva
plc_client = Client(url=URL)

# ---------------------------------------------------------
# GESTIÓN DE LA CONEXIÓN (LIFESPAN)
# ---------------------------------------------------------
# Esto ejecuta la conexión al encender el servidor y la cierra al apagarlo
@asynccontextmanager
async def lifespan(app: FastAPI):
    print(f"Iniciando servidor y conectando al PLC en {URL}...")
    try:
        await plc_client.connect()
        print("✅ ¡Conectado exitosamente al S7-1200!")
    except Exception as e:
        print(f"❌ Error crítico conectando al PLC: {e}")
    
    yield  # Aquí el servidor se queda corriendo y escuchando peticiones
    
    print("Apagando servidor. Desconectando del PLC...")
    try:
        await plc_client.disconnect()
        print("Desconectado de forma segura.")
    except:
        pass

# Instanciamos la aplicación web
app = FastAPI(lifespan=lifespan)

# ---------------------------------------------------------
# CONFIGURACIÓN CORS (CRUCIAL PARA LA WEB)
# ---------------------------------------------------------
# Esto permite que tu futuro código HTML/JS pueda comunicarse con este Python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # En producción puedes restringirlo a la IP de tu web
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------
# MODELO DE DATOS
# ---------------------------------------------------------
# Define qué datos esperamos recibir de la cámara/etiqueta
class EtiquetaDetectada(BaseModel):
    categoria: int  # Solo aceptará números enteros (1, 2 o 3)

# ---------------------------------------------------------
# RUTA (ENDPOINT) PARA PROCESAR LA LECTURA
# ---------------------------------------------------------
@app.post("/procesar_etiqueta")
async def procesar_etiqueta(datos: EtiquetaDetectada):
    """
    Este endpoint es llamado desde la página web cada vez 
    que la cámara detecta y clasifica una etiqueta.
    """
    # 1. Verificar que el PLC esté conectado
    # Nota: asyncua usa uaclient.protocol para verificar si está activo
    try:
        nodo_piston1 = plc_client.get_node("ns=4;i=2")
        nodo_piston2 = plc_client.get_node("ns=4;i=5")
        nodo_motor_speed = plc_client.get_node("ns=4;i=4")
    except Exception as e:
        raise HTTPException(status_code=500, detail="Error de comunicación con el PLC. ¿Está encendido?")

    try:
        # ---------------------------------------------------------
        # LÓGICA DE LAS 3 POSIBILIDADES
        # ---------------------------------------------------------
        if datos.categoria == 1:
            print("📷 Etiqueta 1 detectada -> Activando Pistón 1, Velocidad: 60")
            
            # Encendemos Piston 1, Apagamos Piston 2, Velocidad 60
            dv_p1 = ua.DataValue(ua.Variant(True, ua.VariantType.Boolean))
            dv_p2 = ua.DataValue(ua.Variant(False, ua.VariantType.Boolean))
            dv_vel = ua.DataValue(ua.Variant(60, ua.VariantType.Int16))
            
            await nodo_piston1.write_value(dv_p1)
            await nodo_piston2.write_value(dv_p2)
            await nodo_motor_speed.write_value(dv_vel)
            
            return {"status": "success", "mensaje": "Ruta 1 aplicada con éxito en el PLC"}

        elif datos.categoria == 2:
            print("📷 Etiqueta 2 detectada -> Activando Pistón 2, Velocidad: 1200")
            
            # Apagamos Piston 1, Encendemos Piston 2, Velocidad 1200
            dv_p1 = ua.DataValue(ua.Variant(False, ua.VariantType.Boolean))
            dv_p2 = ua.DataValue(ua.Variant(True, ua.VariantType.Boolean))
            dv_vel = ua.DataValue(ua.Variant(1200, ua.VariantType.Int16))
            
            await nodo_piston1.write_value(dv_p1)
            await nodo_piston2.write_value(dv_p2)
            await nodo_motor_speed.write_value(dv_vel)
            
            return {"status": "success", "mensaje": "Ruta 2 aplicada con éxito en el PLC"}

        elif datos.categoria == 3:
            print("📷 Etiqueta 3 detectada -> Parada general, Velocidad: 0")
            
            # Apagamos todo y detenemos motor
            dv_p1 = ua.DataValue(ua.Variant(False, ua.VariantType.Boolean))
            dv_p2 = ua.DataValue(ua.Variant(False, ua.VariantType.Boolean))
            dv_vel = ua.DataValue(ua.Variant(0, ua.VariantType.Int16))
            
            await nodo_piston1.write_value(dv_p1)
            await nodo_piston2.write_value(dv_p2)
            await nodo_motor_speed.write_value(dv_vel)
            
            return {"status": "success", "mensaje": "Ruta 3 (Parada general) aplicada en el PLC"}

        else:
            # Si la web envía una etiqueta como "4" o "5"
            raise HTTPException(status_code=400, detail="Categoría no válida. Debe ser 1, 2 o 3.")

    except Exception as e:
        print(f"Error escribiendo en el PLC: {e}")
        raise HTTPException(status_code=500, detail="Error interno aplicando la lógica en el PLC")