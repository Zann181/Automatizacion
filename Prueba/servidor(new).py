import asyncio
import os
import json
import sys
import sqlite3
import urllib.request
import datetime
import ipaddress
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from asyncua import Client, ua

# ---------------------------------------------------------
# CONFIGURACIÓN Y CONSTANTES
# ---------------------------------------------------------
URL = "opc.tcp://192.168.0.1:4840"
DB_FILE = "plc_logs.db"

# Nodos del PLC
PLC_NODES = {
    "motor_state": {"node_id": "ns=4;i=3", "type": "Boolean"},
    "motor_speed": {"node_id": "ns=4;i=4", "type": "Int16"},
    "Categoria1": {"node_id": "ns=4;i=8", "type": "Boolean"},
    "Categoria2": {"node_id": "ns=4;i=7", "type": "Boolean"},
    "Categoria3": {"node_id": "ns=4;i=6", "type": "Boolean"},
    "piston1": {"node_id": "ns=4;i=2", "type": "Boolean"},
    "piston2": {"node_id": "ns=4;i=5", "type": "Boolean"},
}

# ---------------------------------------------------------
# ESTADO GLOBAL
# ---------------------------------------------------------
plc_client = None
plc_connected = False
sheets_connected = False

# Estado del PLC en memoria para modo simulación
simulated_plc = {
    "motor_state": True,
    "motor_speed": 30,
    "Categoria1": False,
    "Categoria2": False,
    "Categoria3": False,
    "piston1": False,
    "piston2": False
}

# ---------------------------------------------------------
# BASE DE DATOS Y MIGRACIONES
# ---------------------------------------------------------
def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    # Tabla de historial de escaneos
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS box_scans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            category INTEGER,
            qr_data TEXT,
            synced INTEGER DEFAULT 0
        )
    ''')
    # Tabla de configuraciones de cámara
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS camera_settings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            initial_delay VARCHAR(50) DEFAULT '1.0',
            motor_off_duration VARCHAR(50) DEFAULT '1.0',
            cat1_duration VARCHAR(50) DEFAULT '2.0',
            cat2_duration VARCHAR(50) DEFAULT '2.0',
            cat3_duration VARCHAR(50) DEFAULT '2.0',
            auto_execute VARCHAR(50) DEFAULT '1'
        )
    ''')
    
    # Migración: Verificar si existen las nuevas columnas
    cursor.execute("PRAGMA table_info(camera_settings)")
    columns = [col[1] for col in cursor.fetchall()]
    
    new_cols = {
        "cat1_travel_time": "VARCHAR(50) DEFAULT '2.0'",
        "cat2_travel_time": "VARCHAR(50) DEFAULT '4.0'",
        "cat3_travel_time": "VARCHAR(50) DEFAULT '0.0'",
        "sensitivity": "VARCHAR(50) DEFAULT '15'",
        "google_sheets_url": "TEXT DEFAULT ''",
        "plc_url": "VARCHAR(255) DEFAULT 'opc.tcp://192.168.0.1:4840'"
    }
    
    for col_name, col_def in new_cols.items():
        if col_name not in columns:
            cursor.execute(f"ALTER TABLE camera_settings ADD COLUMN {col_name} {col_def}")
            print(f"Base de Datos: Columna agregada -> {col_name}")
            
    # Garantizar fila por defecto
    cursor.execute("SELECT COUNT(*) FROM camera_settings")
    if cursor.fetchone()[0] == 0:
        cursor.execute('''
            INSERT INTO camera_settings (id, initial_delay, motor_off_duration, cat1_duration, cat2_duration, cat3_duration, auto_execute, cat1_travel_time, cat2_travel_time, cat3_travel_time, sensitivity, google_sheets_url)
            VALUES (1, '1.0', '1.0', '2.0', '2.0', '2.0', '1', '2.0', '4.0', '0.0', '15', '')
        ''')
    conn.commit()
    conn.close()

def get_settings():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM camera_settings WHERE id = 1")
    row = cursor.fetchone()
    conn.close()
    if row:
        return dict(row)
    return {}

def update_settings_db(data: dict):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    keys = [k for k in data.keys() if k != 'id']
    values = [str(data[k]) for k in keys]
    set_clause = ", ".join([f"{k} = ?" for k in keys])
    values.append(1) # ID = 1
    cursor.execute(f"UPDATE camera_settings SET {set_clause} WHERE id = ?", values)
    conn.commit()
    conn.close()

# ---------------------------------------------------------
# GENERACIÓN DE CERTIFICADO SSL AUTO-FIRMADO
# ---------------------------------------------------------
def check_ssl_certs():
    cert_file = "cert.pem"
    key_file = "key.pem"
    if not os.path.exists(cert_file) or not os.path.exists(key_file):
        print("SSL: No se encontraron certificados 'cert.pem' o 'key.pem'. Generando auto-firmados...")
        try:
            from cryptography import x509
            from cryptography.x509.oid import NameOID
            from cryptography.hazmat.primitives import hashes
            from cryptography.hazmat.primitives.asymmetric import rsa
            from cryptography.hazmat.primitives import serialization

            # Generar Clave Privada
            key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
            with open(key_file, "wb") as f:
                f.write(key.private_bytes(
                    encoding=serialization.Encoding.PEM,
                    format=serialization.PrivateFormat.TraditionalOpenSSL,
                    encryption_algorithm=serialization.NoEncryption()
                ))
            
            # Generar Certificado
            subject = issuer = x509.Name([
                x509.NameAttribute(NameOID.COUNTRY_NAME, "CO"),
                x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, "Bogota"),
                x509.NameAttribute(NameOID.LOCALITY_NAME, "Bogota"),
                x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Unal"),
                x509.NameAttribute(NameOID.COMMON_NAME, "localhost"),
            ])
            
            cert = x509.CertificateBuilder().subject_name(
                subject
            ).issuer_name(
                issuer
            ).public_key(
                key.public_key()
            ).serial_number(
                x509.random_serial_number()
            ).not_valid_before(
                datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=1)
            ).not_valid_after(
                datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=365)
            ).add_extension(
                x509.SubjectAlternativeName([
                    x509.DNSName("localhost"),
                    x509.IPAddress(ipaddress.IPv4Address("127.0.0.1")),
                    x509.IPAddress(ipaddress.IPv4Address("0.0.0.0")),
                ]),
                critical=False,
            ).sign(key, hashes.SHA256())
            
            with open(cert_file, "wb") as f:
                f.write(cert.public_bytes(serialization.Encoding.PEM))
            
            print("SSL: Certificados auto-firmados generados exitosamente.")
        except Exception as e:
            print(f"SSL: Error al generar certificados auto-firmados: {e}")
            print("Asegurate de instalar 'cryptography' o proveer cert.pem y key.pem manualmente.")

# ---------------------------------------------------------
# INTERACCIÓN CON PLC (FÍSICO / SIMULADOR)
# ---------------------------------------------------------
async def get_plc_value(name: str, node_id: str, var_type: str):
    global plc_connected, plc_client, simulated_plc
    if plc_connected:
        try:
            node = plc_client.get_node(node_id)
            val = await node.read_value()
            if var_type == "Boolean":
                return bool(val)
            elif var_type in ("Int16", "Int32", "UInt16", "UInt32"):
                return int(val)
            return val
        except Exception as e:
            print(f"PLC: Error de lectura en '{name}': {e}")
    return simulated_plc.get(name, False if var_type == "Boolean" else 0)

async def set_plc_value(name: str, node_id: str, val, var_type: str):
    global plc_connected, plc_client, simulated_plc
    simulated_plc[name] = val
    if plc_connected:
        try:
            node = plc_client.get_node(node_id)
            if var_type == "Boolean":
                ua_val = bool(val)
                variant_type = ua.VariantType.Boolean
            elif var_type == "Int16":
                ua_val = int(val)
                variant_type = ua.VariantType.Int16
            elif var_type == "Int32":
                ua_val = int(val)
                variant_type = ua.VariantType.Int32
            else:
                ua_val = val
                variant_type = ua.VariantType.String
            
            dv = ua.DataValue(ua.Variant(ua_val, variant_type))
            await node.write_value(dv)
            print(f"PLC Escrito: {name} = {val}")
            return True
        except Exception as e:
            print(f"PLC: Error de escritura en '{name}': {e}")
            plc_connected = False
    else:
        print(f"SIMULADOR Escrito: {name} = {val}")
    return False

# Lógica del clasificador secuencial (motor y actuadores)
async def run_conveyor_logic(category: int):
    # 1. Asegurar parada del motor para enfocar el código QR
    await set_plc_value("motor_state", PLC_NODES["motor_state"]["node_id"], False, "Boolean")
    
    settings = get_settings()
    initial_delay = float(settings.get("initial_delay", 1.0))
    
    # Esperar el tiempo de parada para lectura del QR
    print(f"Automatización: Motor detenido por {initial_delay}s para lectura...")
    await asyncio.sleep(initial_delay)
    
    # 2. Reanudar la marcha para trasladar la caja
    print("Automatización: Marcha reanudada. Transportando caja...")
    await set_plc_value("motor_state", PLC_NODES["motor_state"]["node_id"], True, "Boolean")
    
    if category == 1:
        travel_time = float(settings.get("cat1_travel_time", 2.0))
        active_time = float(settings.get("cat1_duration", 2.0))
        
        print(f"Categoría 1: Viajando por {travel_time}s hacia actuador...")
        await asyncio.sleep(travel_time)
        
        print("Categoría 1: Activando actuador...")
        await set_plc_value("Categoria1", PLC_NODES["Categoria1"]["node_id"], True, "Boolean")
        await asyncio.sleep(active_time)
        await set_plc_value("Categoria1", PLC_NODES["Categoria1"]["node_id"], False, "Boolean")
        print("Categoría 1: Actuador apagado.")
        
    elif category == 2:
        travel_time = float(settings.get("cat2_travel_time", 4.0))
        active_time = float(settings.get("cat2_duration", 2.0))
        
        print(f"Categoría 2: Viajando por {travel_time}s hacia actuador...")
        await asyncio.sleep(travel_time)
        
        print("Categoría 2: Activando actuador...")
        await set_plc_value("Categoria2", PLC_NODES["Categoria2"]["node_id"], True, "Boolean")
        await asyncio.sleep(active_time)
        await set_plc_value("Categoria2", PLC_NODES["Categoria2"]["node_id"], False, "Boolean")
        print("Categoría 2: Actuador apagado.")
        
    elif category == 3:
        # Categoría 3 corre libremente hacia el final
        travel_time = float(settings.get("cat3_travel_time", 0.0))
        active_time = float(settings.get("cat3_duration", 2.0))
        print("Categoría 3: Caja continúa hasta el final del recorrido...")
        
        if travel_time > 0:
            await asyncio.sleep(travel_time)
        # Activar pin temporal para retroalimentación visual en PLC
        await set_plc_value("Categoria3", PLC_NODES["Categoria3"]["node_id"], True, "Boolean")
        await asyncio.sleep(active_time)
        await set_plc_value("Categoria3", PLC_NODES["Categoria3"]["node_id"], False, "Boolean")

# ---------------------------------------------------------
# TAREAS EN SEGUNDO PLANO (WORKERS)
# ---------------------------------------------------------
async def plc_reconnection_loop():
    global plc_connected, plc_client
    while True:
        if not plc_connected:
            print(f"PLC: Intentando conectar en {URL}...")
            try:
                # Establecer nuevo cliente para evitar bloqueos
                plc_client = Client(url=URL)
                # Timeout de conexión corto
                await asyncio.wait_for(plc_client.connect(), timeout=3.0)
                plc_connected = True
                print("PLC: Conectado exitosamente!")
                # Leer velocidad inicial de arranque
                speed = await get_plc_value("motor_speed", PLC_NODES["motor_speed"]["node_id"], "Int16")
                simulated_plc["motor_speed"] = speed
            except Exception as e:
                plc_connected = False
                # print(f"PLC: Fallo en conexión ({e}). Reintentando...")
        else:
            try:
                # PING rápido leyendo velocidad
                node = plc_client.get_node(PLC_NODES["motor_speed"]["node_id"])
                await asyncio.wait_for(node.read_value(), timeout=2.0)
            except Exception:
                print("PLC: Conexion caida detectada en el loop de verificacion.")
                plc_connected = False
                try:
                    await plc_client.disconnect()
                except:
                    pass
        await asyncio.sleep(5)

async def sheets_sync_loop():
    global sheets_connected
    while True:
        settings = get_settings()
        url = settings.get("google_sheets_url", "").strip()
        
        if not url:
            sheets_connected = False
            await asyncio.sleep(10)
            continue
            
        # Consultar si hay escaneos pendientes
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("SELECT id, timestamp, category, qr_data FROM box_scans WHERE synced = 0 ORDER BY id ASC LIMIT 10")
        rows = cursor.fetchall()
        conn.close()
        
        if not rows:
            # Si hay URL pero no hay datos, asumimos conexión "OK" si estaba en True, o la dejamos inalterada.
            await asyncio.sleep(10)
            continue
            
        success_ids = []
        sync_failed = False
        
        for r_id, timestamp, category, qr_data in rows:
            payload = {
                "timestamp": timestamp,
                "category": int(category),
                "qr_data": qr_data
            }
            try:
                req = urllib.request.Request(
                    url, 
                    data=json.dumps(payload).encode('utf-8'),
                    headers={'Content-Type': 'application/json'},
                    method='POST'
                )
                with urllib.request.urlopen(req, timeout=4.0) as response:
                    if response.getcode() in (200, 201):
                        success_ids.append(r_id)
                    else:
                        sync_failed = True
            except Exception as e:
                print(f"Sheets: Error al sincronizar ID {r_id}: {e}")
                sync_failed = True
                break
                
        if success_ids:
            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()
            placeholders = ", ".join(["?" for _ in success_ids])
            cursor.execute(f"UPDATE box_scans SET synced = 1 WHERE id IN ({placeholders})", success_ids)
            conn.commit()
            conn.close()
            print(f"Sheets: {len(success_ids)} registros sincronizados con éxito.")
            
        sheets_connected = not sync_failed
        await asyncio.sleep(10)

# Inicializar Base de Datos al cargar el módulo
print("Iniciando base de datos...")
init_db()

# Cargar la dirección URL del PLC desde los ajustes en la BD
try:
    settings = get_settings()
    if settings.get("plc_url"):
        URL = settings["plc_url"]
        print(f"PLC: URL configurada de la BD -> {URL}")
except Exception as e:
    print(f"Error cargando URL del PLC desde BD: {e}")

# Verificar y generar certificados SSL al cargar el módulo (antes de iniciar uvicorn)
print("Verificando certificados SSL...")
check_ssl_certs()

# ---------------------------------------------------------
# LIFESPAN DEL SERVIDOR
# ---------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Lanzar hilos de trabajo asíncronos
    reconnect_task = asyncio.create_task(plc_reconnection_loop())
    sync_task = asyncio.create_task(sheets_sync_loop())
    
    yield
    
    # Cancelar tareas
    reconnect_task.cancel()
    sync_task.cancel()
    if plc_client and plc_connected:
        try:
            await plc_client.disconnect()
        except:
            pass

# Initialize FastAPI
app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------
# ARCHIVOS ESTÁTICOS Y ENRUTAMIENTO
# ---------------------------------------------------------
# Montar recursos estáticos si las carpetas existen
if os.path.exists("css"):
    app.mount("/css", StaticFiles(directory="css"), name="css")
if os.path.exists("js"):
    app.mount("/js", StaticFiles(directory="js"), name="js")

@app.get("/")
@app.get("/index.html")
async def servir_dashboard():
    return FileResponse("index.html")

@app.get("/camera.html")
async def servir_camera():
    return FileResponse("camera.html")

# ---------------------------------------------------------
# MODELOS DE DATOS API
# ---------------------------------------------------------
class EtiquetaDetectada(BaseModel):
    categoria: int
    qr_data: str

class MotorSpeedInput(BaseModel):
    speed: int

class MotorToggleInput(BaseModel):
    state: bool

# ---------------------------------------------------------
# ENDPOINTS API REST
# ---------------------------------------------------------
@app.get("/api/status")
async def get_status():
    speed = await get_plc_value("motor_speed", PLC_NODES["motor_speed"]["node_id"], "Int16")
    motor = await get_plc_value("motor_state", PLC_NODES["motor_state"]["node_id"], "Boolean")
    c1 = await get_plc_value("Categoria1", PLC_NODES["Categoria1"]["node_id"], "Boolean")
    c2 = await get_plc_value("Categoria2", PLC_NODES["Categoria2"]["node_id"], "Boolean")
    c3 = await get_plc_value("Categoria3", PLC_NODES["Categoria3"]["node_id"], "Boolean")
    
    # Estadísticas locales
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM box_scans")
    total = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM box_scans WHERE category = 1")
    cat1 = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM box_scans WHERE category = 2")
    cat2 = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM box_scans WHERE category = 3")
    cat3 = cursor.fetchone()[0]
    conn.close()
    
    # Si la URL de sheets está vacía, no reportar "conectado"
    settings = get_settings()
    has_sheets_url = bool(settings.get("google_sheets_url", "").strip())
    
    return {
        "plc_connected": plc_connected,
        "sheets_connected": sheets_connected if has_sheets_url else False,
        "has_sheets_url": has_sheets_url,
        "motor_state": motor,
        "motor_speed": speed,
        "categoria1_state": c1,
        "categoria2_state": c2,
        "categoria3_state": c3,
        "total_scans": total,
        "cat1_count": cat1,
        "cat2_count": cat2,
        "cat3_count": cat3
    }

@app.post("/api/motor/speed")
async def set_motor_speed(data: MotorSpeedInput):
    if data.speed < 1 or data.speed > 60:
        raise HTTPException(status_code=400, detail="La velocidad debe estar entre 1 y 60.")
    success = await set_plc_value("motor_speed", PLC_NODES["motor_speed"]["node_id"], data.speed, "Int16")
    return {"status": "success" if success else "simulated", "speed": data.speed}

@app.post("/api/motor/toggle")
async def toggle_motor(data: MotorToggleInput):
    success = await set_plc_value("motor_state", PLC_NODES["motor_state"]["node_id"], data.state, "Boolean")
    return {"status": "success" if success else "simulated", "state": data.state}

@app.get("/api/settings")
async def get_settings_api():
    return get_settings()

@app.post("/api/settings")
async def save_settings_api(settings: dict):
    global sheets_connected, URL, plc_connected, plc_client
    update_settings_db(settings)
    
    # Actualizar la URL de conexión del PLC de forma dinámica si cambió
    new_plc_url = settings.get("plc_url", "").strip()
    if new_plc_url and new_plc_url != URL:
        URL = new_plc_url
        plc_connected = False
        print(f"PLC: URL de conexion cambiada en vivo a -> {URL}")
        try:
            await plc_client.disconnect()
        except:
            pass
            
    # Probar conexión al instante si configuran una URL
    url = settings.get("google_sheets_url", "").strip()
    if url:
        try:
            req = urllib.request.Request(
                url, 
                data=json.dumps({"test": True, "category": 0, "qr_data": "TEST_CONN"}).encode('utf-8'),
                headers={'Content-Type': 'application/json'},
                method='POST'
            )
            with urllib.request.urlopen(req, timeout=3.0) as response:
                if response.getcode() in (200, 201):
                    sheets_connected = True
                else:
                    sheets_connected = False
        except Exception:
            sheets_connected = False
    else:
        sheets_connected = False
        
    return {"status": "success", "sheets_connected": sheets_connected}

@app.get("/api/logs")
async def get_logs_api():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM box_scans ORDER BY id DESC LIMIT 100")
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

@app.post("/api/logs/clear")
async def clear_logs_api():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM box_scans")
    conn.commit()
    conn.close()
    return {"status": "success"}

@app.post("/api/box_entered")
async def box_entered_api():
    # Parar marcha de inmediato al entrar una caja
    success = await set_plc_value("motor_state", PLC_NODES["motor_state"]["node_id"], False, "Boolean")
    return {"status": "success" if success else "simulated"}

@app.post("/api/notificar_categoria")
async def notificar_categoria(datos: EtiquetaDetectada):
    # Guardar en base de datos local (marcar no sincronizado por defecto)
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO box_scans (category, qr_data, synced) VALUES (?, ?, 0)", (datos.categoria, datos.qr_data))
    conn.commit()
    conn.close()
    
    # Disparar secuencia del clasificador en segundo plano
    asyncio.create_task(run_conveyor_logic(datos.categoria))
    
    return {
        "status": "success", 
        "mensaje": f"Categoría {datos.categoria} guardada y secuencia PLC iniciada."
    }

# ---------------------------------------------------------
# ARRANQUE DE APLICACIÓN
# ---------------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    # Inicia uvicorn en puerto 8000 con soporte SSL
    uvicorn.run(
        "servidor(new):app", 
        host="0.0.0.0", 
        port=8000,
        ssl_keyfile="key.pem",
        ssl_certfile="cert.pem",
        reload=True
    )