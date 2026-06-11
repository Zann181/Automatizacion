# -*- coding: utf-8 -*-
"""
========================================================================
     MONITOR INDUSTRIAL & SIMULADOR OPC-UA (WINDOWS RUNTIME v1.0)
========================================================================
Este script levanta un servidor HTTPS Seguro y replica la REST API del
backend C++ del ProyectoOPCUA en Windows. Incluye la máquina de estados
FSM de la banda, base de datos SQLite y sniffer de puerto Ethernet.

Requisitos: Cero dependencias externas (usa librerías estándar de Python).
Opcional: pip install opcua-asyncio (para comunicación con PLC real).
========================================================================
"""
import os
import sys
import time
import json
import sqlite3
import threading
import socket
import ssl
import subprocess
import importlib.util
import urllib.parse
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

# Colores ANSI para Consola Industrial
CYAN = "\033[96m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
MAGENTA = "\033[95m"
RESET = "\033[0m"
WHITE = "\033[97m"
GRAY = "\033[90m"

# Nombre de la Base de Datos
DB_FILE = "config_plc.db"

# ========================================================================
# ESTADO GLOBAL DEL SIMULADOR (HILO-SEGURO)
# ========================================================================
class SimulatorState:
    def __init__(self):
        self.lock = threading.Lock()
        self.fsm_state = "IDLE"
        self.motor_running = True
        self.motor_speed = 1200.0
        self.target_speed = 1200.0
        self.piston1_active = False
        self.piston2_active = False
        
        # Conteos de categorías (cargados de DB)
        self.count_cat1 = 0
        self.count_cat2 = 0
        self.count_cat3 = 0
        self.count_otro = 0
        self.total_classified = 0
        
        # Historial de escaneo
        self.last_event_time = ""
        self.last_qr_data = ""
        self.last_categoria = 0
        
        # Configuración OPC-UA y Red
        self.opc_ip = "192.168.0.1"
        self.opc_port = 4840
        self.opc_endpoint = "opc.tcp://192.168.0.1:4840"
        self.opc_connected = False
        
    def sync_from_db(self):
        with self.lock:
            try:
                conn = sqlite3.connect(DB_FILE)
                cursor = conn.cursor()
                # Leer configuracion OPC
                cursor.execute("SELECT ip, port, endpoint, enabled FROM config_opc WHERE id=1")
                row = cursor.fetchone()
                if row:
                    self.opc_ip, self.opc_port, self.opc_endpoint, _ = row
                    
                # Leer conteos acumulados de clasificacion
                cursor.execute("SELECT categoria, COUNT(*) FROM classification_events GROUP BY categoria")
                self.count_cat1 = 0
                self.count_cat2 = 0
                self.count_cat3 = 0
                self.count_otro = 0
                self.total_classified = 0
                for cat, cnt in cursor.fetchall():
                    if cat == 1: self.count_cat1 = cnt
                    elif cat == 2: self.count_cat2 = cnt
                    elif cat == 3: self.count_cat3 = cnt
                    else: self.count_otro += cnt
                    self.total_classified += cnt
                    
                # Leer ultimo evento
                cursor.execute("SELECT timestamp, qr_data, categoria FROM classification_events ORDER BY id DESC LIMIT 1")
                row_last = cursor.fetchone()
                if row_last:
                    self.last_event_time, self.last_qr_data, self.last_categoria = row_last
                    
                conn.close()
            except Exception as e:
                log_err(f"Error sincronizando de base de datos: {e}")

state = SimulatorState()

# ========================================================================
# FUNCIONES DE LOG DE CONSOLA
# ========================================================================
def log_info(msg):
    t = time.strftime("%H:%M:%S")
    print(f"{GRAY}[{t}]{RESET} {CYAN}[INFO]{RESET} {msg}")

def log_success(msg):
    t = time.strftime("%H:%M:%S")
    print(f"{GRAY}[{t}]{RESET} {GREEN}[OK]{RESET} {msg}")

def log_warn(msg):
    t = time.strftime("%H:%M:%S")
    print(f"{GRAY}[{t}]{RESET} {YELLOW}[ALERTA]{RESET} {msg}")

def log_err(msg):
    t = time.strftime("%H:%M:%S")
    print(f"{GRAY}[{t}]{RESET} {RED}[ERROR]{RESET} {msg}")

def log_fsm(msg):
    t = time.strftime("%H:%M:%S")
    print(f"{GRAY}[{t}]{RESET} {MAGENTA}[FSM]{RESET} {msg}")

def log_sniffer(ip_src, ip_dst, proto, msg):
    t = time.strftime("%H:%M:%S")
    print(f"{GRAY}[{t}]{RESET} {GRAY}[SNIFFER Ethernet]{RESET} {WHITE}{ip_src} -> {ip_dst}{RESET} {YELLOW}[{proto}]{RESET} {msg}")

# ========================================================================
# INICIALIZACIÓN DE BASE DE DATOS SQLITE (Idéntica a C++)
# ========================================================================
def init_database():
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        
        # 1. Esquema
        cursor.executescript("""
            CREATE TABLE IF NOT EXISTS config_opc (
                id INTEGER PRIMARY KEY,
                ip TEXT, port INTEGER, endpoint TEXT, timeout_ms INTEGER,
                auto_reconnect BOOLEAN, security_policy TEXT, auth_mode TEXT, enabled BOOLEAN
            );
            INSERT OR IGNORE INTO config_opc (id, ip, port, endpoint, timeout_ms, auto_reconnect, security_policy, auth_mode, enabled)
            VALUES (1, '192.168.0.1', 4840, 'opc.tcp://192.168.0.1:4840', 5000, 1, 'None', 'Anonymous', 1);

            CREATE TABLE IF NOT EXISTS config_network (
                id INTEGER PRIMARY KEY,
                iface_eth TEXT, ip_eth TEXT, mask_eth TEXT,
                iface_wifi TEXT, ssid_wifi TEXT, pass_wifi TEXT, web_port INTEGER
            );
            INSERT OR IGNORE INTO config_network (id, iface_eth, ip_eth, mask_eth, iface_wifi, ssid_wifi, pass_wifi, web_port)
            VALUES (1, 'eth0', '192.168.0.10', '255.255.255.0', 'wlan0', 'PLC_Control', '123456789', 8080);

            CREATE TABLE IF NOT EXISTS opc_variables (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT, description TEXT, node_id TEXT, ns_index INTEGER,
                data_type TEXT, unit TEXT, writable BOOLEAN, scan_rate_ms INTEGER, enabled BOOLEAN
            );

            CREATE TABLE IF NOT EXISTS data_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                variable_id INTEGER, value_str TEXT,
                FOREIGN KEY(variable_id) REFERENCES opc_variables(id)
            );

            CREATE TABLE IF NOT EXISTS system_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                level TEXT, message TEXT
            );

            CREATE TABLE IF NOT EXISTS classification_events (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT    NOT NULL,
                qr_data   TEXT    NOT NULL,
                categoria INTEGER NOT NULL,
                result    TEXT    NOT NULL
            );
        """)
        
        # Pre-poblar variables por defecto
        cursor.execute("SELECT COUNT(*) FROM opc_variables")
        if cursor.fetchone()[0] == 0:
            cursor.executemany("""
                INSERT INTO opc_variables (name, description, node_id, ns_index, data_type, unit, writable, scan_rate_ms, enabled)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, [
                ('Motor_State', 'Estado ON/OFF del motor de la banda', 's="Bloque de datos_1"."Motor_State"', 3, 'Boolean', '', 1, 500, 1),
                ('Motor_Speed', 'Velocidad actual del motor (RPM)', 's="Bloque de datos_1"."Motor_Speed"', 3, 'Int32', 'RPM', 0, 500, 1),
                ('Piston1', 'Actuador neumatico Piston 1 (Categoria 1)', 's="Bloque de datos_1"."Piston1"', 3, 'Boolean', '', 1, 200, 1),
                ('Piston2', 'Actuador neumatico Piston 2 (Categoria 2)', 's="Bloque de datos_1"."Piston2"', 3, 'Boolean', '', 1, 200, 1)
            ])
            
        conn.commit()
        conn.close()
        log_success(f"Base de datos SQLite inicializada exitosamente: '{DB_FILE}'")
    except Exception as e:
        log_err(f"Fallo crítico al iniciar base de datos: {e}")
        sys.exit(1)

def sync_opc_config():
    """Load OPC connection params from conexion_plc.py and update DB."""
    try:
        # Load conexion_plc module dynamically
        module_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'Prueba', 'conexion_plc.py'))
        spec = importlib.util.spec_from_file_location('conexion_plc', module_path)
        conn_mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(conn_mod)
        url = getattr(conn_mod, 'URL', None)
        timeout_ms = getattr(conn_mod, 'TIMEOUT_MS', 5000)
        if not url:
            log_warn('URL not found in conexion_plc.py; skipping OPC config sync')
            return
        parsed = urllib.parse.urlparse(url)
        ip = parsed.hostname or ''
        port = parsed.port or 0
        endpoint = url
        # Update SQLite config_opc table
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE config_opc SET ip = ?, port = ?, endpoint = ?, timeout_ms = ? WHERE id = 1
        """, (ip, port, endpoint, timeout_ms))
        conn.commit()
        conn.close()
        log_success('OPC config synchronized from conexion_plc.py')
    except Exception as e:
        log_err(f'Error syncing OPC config: {e}')

# ========================================================================
# HILOS DE ACTUACIÓN ASÍNCRONA DE LOS PISTONES (FSM)
# ========================================================================
def actuate_piston_thread(piston_num, delay_seconds):
    log_fsm(f"Pistón {piston_num} programado para dispararse en {delay_seconds}s (hilo en segundo plano).")
    
    # 1. Espera
    time.sleep(delay_seconds)
    
    # 2. Activación
    with state.lock:
        if piston_num == 1: state.piston1_active = True
        else: state.piston2_active = True
    
    log_fsm(f"¡Pistón {piston_num} ACTIVADO!")
    # Simular tráfico Ethernet de comando al PLC
    log_sniffer("192.168.10.10", state.opc_ip, "OPC-UA", f"WriteRequest -> ns=2;s=Piston{piston_num} (Value=True)")
    
    # 3. Mantener activo 500ms (pulso neumático)
    time.sleep(0.5)
    
    # 4. Desactivación
    with state.lock:
        if piston_num == 1: state.piston1_active = False
        else: state.piston2_active = False
        
    log_fsm(f"Pistón {piston_num} desactivado.")
    log_sniffer("192.168.10.10", state.opc_ip, "OPC-UA", f"WriteRequest -> ns=2;s=Piston{piston_num} (Value=False)")

# ========================================================================
# MÁQUINA DE ESTADOS FINITA (FSM) DE CLASIFICACIÓN
# ========================================================================
def process_qr_fsm(qr_data):
    # Asegurar que no se procesen dos al mismo tiempo
    with state.lock:
        if state.fsm_state in ["DETECTING", "STOPPED", "CLASSIFYING"]:
            log_warn("Evento QR ignorado: FSM ocupada procesando otra caja.")
            return False
            
    # --- PASO 1: DETECTAR Y PARAR MOTOR ---
    log_fsm("Cambio de Estado: IDLE -> DETECTING")
    state.fsm_state = "DETECTING"
    
    log_fsm("Enviando comando de detención Motor_State=False...")
    log_sniffer("192.168.10.10", state.opc_ip, "OPC-UA", "WriteRequest -> ns=2;s=Motor_State (Value=False)")
    
    with state.lock:
        state.motor_running = False
        state.target_speed = 0.0
        state.fsm_state = "STOPPED"
    log_fsm("Estado: STOPPED (Banda desacelerando)")
    
    # Simular desaceleración física
    time.sleep(0.2)
    
    # --- PASO 2: CLASIFICAR ---
    state.fsm_state = "CLASSIFYING"
    log_fsm(f"Estado: CLASSIFYING -> Analizando código QR: '{qr_data}'")
    
    # Determinar categoría
    categoria = 0
    try:
        val = int(qr_data.strip())
        if val in [1, 2, 3]:
            categoria = val
    except ValueError:
        pass
        
    result_str = "pass"
    if categoria == 1: result_str = "piston1"
    elif categoria == 2: result_str = "piston2"
    
    cat_label = f"Categoría {categoria}" if categoria in [1, 2, 3] else "Inválido / Desconocido"
    log_fsm(f"Caja clasificada como: {cat_label} (Acción: {result_str})")
    
    # --- PASO 3: REGISTRAR EN DB SQLITE (Resiliencia de Datos) ---
    iso_stamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO classification_events (timestamp, qr_data, categoria, result) VALUES (?, ?, ?, ?)",
            (iso_stamp, qr_data, categoria, result_str)
        )
        conn.commit()
        conn.close()
        log_success(f"Evento registrado en DB: QR='{qr_data}' | Cat={categoria} | Result='{result_str}'")
    except Exception as e:
        log_err(f"No se pudo guardar el evento en base de datos SQLite: {e}")
        
    state.sync_from_db()
    
    # --- PASO 4: REINICIAR MOTOR ---
    state.fsm_state = "RUNNING"
    log_fsm("Estado: RUNNING -> Enviando comando de arranque Motor_State=True...")
    log_sniffer("192.168.10.10", state.opc_ip, "OPC-UA", "WriteRequest -> ns=2;s=Motor_State (Value=True)")
    
    with state.lock:
        state.motor_running = True
        state.target_speed = 1200.0
        
    # --- PASO 5: PROGRAMAR ACTUADOR EN HILO DE FONDO ---
    if categoria in [1, 2]:
        delay = 2.0 if categoria == 1 else 4.0
        t = threading.Thread(target=actuate_piston_thread, args=(categoria, delay))
        t.daemon = True
        t.start()
    else:
        log_fsm("Caja sin pistón asignado. Se deja pasar libremente por la banda.")
        
    state.fsm_state = "IDLE"
    log_fsm("Estado: IDLE (Esperando siguiente caja)")
    return True

# ========================================================================
# SIMULACIÓN DE DINÁMICA DE LA BANDA (Motor Speed Ramping & Network Traffic)
# ========================================================================
def band_simulation_loop():
    while True:
        # 1. Rampa de velocidad física del motor (desaceleración y aceleración gradual)
        with state.lock:
            diff = state.target_speed - state.motor_speed
            if abs(diff) > 1.0:
                # Modificación gradual para simular inercia mecánica
                state.motor_speed += (diff * 0.3)
            else:
                state.motor_speed = state.target_speed
                
        # 2. Generación aleatoria de telemetría de red simulada en el puerto OPC-UA
        # (Imita la actividad del polling de KPIs y tramas TCP de background)
        if int(time.time()) % 4 == 0:
            speed = round(state.motor_speed, 1)
            log_sniffer(state.opc_ip, "192.168.10.10", "TCP", f"Flags [P.], seq 1004:1044, ack 2056, win 501, length 40 (OPC UA ReadResponse: Motor_Speed = {speed} RPM)")
            
        time.sleep(0.3)

# ========================================================================
# SERVIDOR HTTP EN PYTHON (Réplica de REST API)
# ========================================================================
class IndustrialApiHandler(BaseHTTPRequestHandler):
    
    # Silenciar logs estándar en consola para que no ensucien la telemetría
    def log_message(self, format, *args):
        pass

    def send_cors_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Cross-Origin-Opener-Policy", "same-origin")
        self.send_header("Cross-Origin-Embedder-Policy", "require-corp")

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_cors_headers()
        self.end_headers()

    def do_GET(self):
        parsed_url = urlparse(self.path)
        path = parsed_url.path
        
        # === ROUTE: /api/opc ===
        if path == "/api/opc":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_cors_headers()
            self.end_headers()
            
            with state.lock:
                payload = {
                    "ip": state.opc_ip,
                    "port": state.opc_port,
                    "endpoint": state.opc_endpoint,
                    "timeout_ms": 5000,
                    "enabled": True,
                    "connected": True  # Modo simulado: siempre conectado
                }
            self.wfile.write(json.dumps(payload).encode("utf-8"))
            return
            
        # === ROUTE: /api/variables ===
        elif path == "/api/variables":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_cors_headers()
            self.end_headers()
            
            vars_list = []
            try:
                conn = sqlite3.connect(DB_FILE)
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM opc_variables")
                for row in cursor.fetchall():
                    vars_list.append({
                        "id": row["id"],
                        "name": row["name"],
                        "description": row["description"],
                        "node_id": row["node_id"],
                        "ns_index": row["ns_index"],
                        "data_type": row["data_type"],
                        "unit": row["unit"],
                        "writable": bool(row["writable"]),
                        "scan_rate_ms": row["scan_rate_ms"],
                        "enabled": bool(row["enabled"])
                    })
                conn.close()
            except Exception as e:
                log_err(f"Error cargando variables: {e}")
                
            self.wfile.write(json.dumps(vars_list).encode("utf-8"))
            return
            
        # === ROUTE: /api/kpi ===
        elif path == "/api/kpi":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_cors_headers()
            self.end_headers()
            
            with state.lock:
                payload = {
                    "motor_speed": round(state.motor_speed, 1),
                    "motor_running": state.motor_running,
                    "piston1_active": state.piston1_active,
                    "piston2_active": state.piston2_active,
                    "count_cat1": state.count_cat1,
                    "count_cat2": state.count_cat2,
                    "count_cat3": state.count_cat3,
                    "count_otro": state.count_otro,
                    "total_classified": state.total_classified,
                    "last_event_time": state.last_event_time,
                    "last_qr_data": state.last_qr_data,
                    "last_categoria": state.last_categoria,
                    "fsm_state": state.fsm_state
                }
            self.wfile.write(json.dumps(payload).encode("utf-8"))
            return
            
        # === ROUTE: /api/events ===
        elif path == "/api/events":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_cors_headers()
            self.end_headers()
            
            query = parse_qs(parsed_url.query)
            limit = 50
            if "limit" in query:
                try: limit = int(query["limit"][0])
                except: pass
                
            events_list = []
            try:
                conn = sqlite3.connect(DB_FILE)
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute("SELECT id, timestamp, qr_data, categoria, result FROM classification_events ORDER BY id DESC LIMIT ?", (limit,))
                for row in cursor.fetchall():
                    events_list.append({
                        "id": row["id"],
                        "timestamp": row["timestamp"],
                        "qr_data": row["qr_data"],
                        "categoria": row["categoria"],
                        "result": row["result"]
                    })
                conn.close()
            except Exception as e:
                log_err(f"Error cargando eventos: {e}")
                
            self.wfile.write(json.dumps(events_list).encode("utf-8"))
            return
            
        # === ROUTE: /api/network ===
        elif path == "/api/network":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_cors_headers()
            self.end_headers()
            
            payload = {
                "ip_eth": "192.168.10.10",
                "ssid_wifi": "Simulador_Windows",
                "web_port": 8443
            }
            self.wfile.write(json.dumps(payload).encode("utf-8"))
            return

        # === SERVIR ARCHIVOS ESTÁTICOS DE LA CARPETA /web ===
        else:
            if path == "/" or path == "":
                path = "/index.html"
            
            # Quitar barra inicial y buscar en ./web
            local_path = "web" + path
            
            if os.path.exists(local_path) and os.path.isfile(local_path):
                # Auto-detectar Content-Type
                content_type = "text/plain"
                if local_path.endswith(".html"): content_type = "text/html"
                elif local_path.endswith(".css"): content_type = "text/css"
                elif local_path.endswith(".js"): content_type = "application/javascript"
                elif local_path.endswith(".min.js"): content_type = "application/javascript"
                elif local_path.endswith(".png"): content_type = "image/png"
                elif local_path.endswith(".jpg"): content_type = "image/jpeg"
                elif local_path.endswith(".ico"): content_type = "image/x-icon"
                
                self.send_response(200)
                self.send_header("Content-Type", content_type)
                self.send_cors_headers()
                self.end_headers()
                
                try:
                    with open(local_path, "rb") as f:
                        self.wfile.write(f.read())
                except Exception as e:
                    self.send_error(500, f"Error de lectura de archivo: {e}")
            else:
                self.send_response(404)
                self.send_cors_headers()
                self.end_headers()
                self.wfile.write(b"404 Not Found")
                
    def do_POST(self):
        parsed_url = urlparse(self.path)
        path = parsed_url.path
        
        # Leer cuerpo del POST
        content_length = int(self.headers.get('Content-Length', 0))
        post_data = self.rfile.read(content_length).decode('utf-8')
        
        # === ROUTE: /api/opc/reconnect ===
        if path == "/api/opc/reconnect":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_cors_headers()
            self.end_headers()
            
            log_info("Comando de reconexión OPC-UA recibido.")
            self.wfile.write(json.dumps({"status": "reconnected"}).encode("utf-8"))
            return
            
        # === ROUTE: /api/variables (Agregar) ===
        elif path == "/api/variables":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_cors_headers()
            self.end_headers()
            
            try:
                data = json.loads(post_data)
                name = data.get("name", "").strip()
                node_id = data.get("node_id", "").strip()
                
                if name and node_id:
                    conn = sqlite3.connect(DB_FILE)
                    cursor = conn.cursor()
                    cursor.execute(
                        "INSERT INTO opc_variables (name, description, node_id, ns_index, data_type, unit, writable, scan_rate_ms, enabled) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (name, "Variable personalizada", node_id, 2, "Float", "", 0, 1000, 1)
                    )
                    conn.commit()
                    conn.close()
                    log_success(f"Variable guardada en DB: {name} ({node_id})")
                    self.wfile.write(json.dumps({"status": "added"}).encode("utf-8"))
                else:
                    self.send_response(400)
                    self.wfile.write(json.dumps({"error": "name y node_id requeridos"}).encode("utf-8"))
            except Exception as e:
                log_err(f"Error agregando variable: {e}")
                self.send_response(500)
            return

        # === ROUTE: /api/classify ===
        elif path == "/api/classify":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_cors_headers()
            self.end_headers()
            
            qr_data = ""
            try:
                # Intentar parsear como JSON
                data = json.loads(post_data)
                qr_data = str(data.get("qr", ""))
            except:
                # Fallback: parsear manual si viene mal formateado
                if '"qr":"' in post_data:
                    parts = post_data.split('"qr":"')
                    if len(parts) > 1:
                        qr_data = parts[1].split('"')[0]
                elif '"qr":' in post_data:
                    parts = post_data.split('"qr":')
                    if len(parts) > 1:
                        qr_data = parts[1].replace(' ', '').replace('}', '').replace('{', '').replace('\n', '').replace('\r', '')
            
            if not qr_data:
                self.send_response(400)
                self.wfile.write(json.dumps({"error": "Campo 'qr' requerido"}).encode("utf-8"))
                return
                
            log_info(f"Petición API POST /api/classify -> QR='{qr_data}'")
            
            # Ejecutar FSM en un hilo aparte para no bloquear la petición HTTP
            t = threading.Thread(target=process_qr_fsm, args=(qr_data,))
            t.daemon = True
            t.start()
            
            self.wfile.write(json.dumps({"status": "processed", "qr": qr_data}).encode("utf-8"))
            return
            
    def do_DELETE(self):
        parsed_url = urlparse(self.path)
        path = parsed_url.path
        
        # === ROUTE: /api/variables/<id> ===
        if path.startswith("/api/variables/"):
            try:
                var_id = int(path.split("/")[-1])
                conn = sqlite3.connect(DB_FILE)
                cursor = conn.cursor()
                cursor.execute("DELETE FROM opc_variables WHERE id=?", (var_id,))
                conn.commit()
                conn.close()
                
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_cors_headers()
                self.end_headers()
                
                log_success(f"Variable ID: {var_id} eliminada de DB.")
                self.wfile.write(json.dumps({"status": "deleted"}).encode("utf-8"))
            except Exception as e:
                log_err(f"Error eliminando variable: {e}")
                self.send_response(500)
            return

# ========================================================================
# GENERACIÓN DE CERTIFICADOS SSL AUTOMÁTICA CON SAN (USANDO OPENSSL DE GIT)
# ========================================================================
def generate_certificates_windows(cert_file, key_file):
    if os.path.exists(cert_file) and os.path.exists(key_file):
        return
        
    log_info("Certificados SSL no encontrados en 'certs/'. Iniciando generación automática...")
    if not os.path.exists("certs"):
        os.makedirs("certs")
        
    # Rutas para buscar openssl
    openssl_path = "openssl"
    paths_to_check = [
        "openssl",
        r"C:\Program Files\Git\usr\bin\openssl.exe",
        r"C:\Program Files\Git\bin\openssl.exe",
        r"C:\Git\usr\bin\openssl.exe"
    ]
    
    for p in paths_to_check:
        try:
            subprocess.run([p, "version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
            openssl_path = p
            break
        except:
            continue
            
    # Obtener IP local del PC activa
    local_ip = "127.0.0.1"
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        s.close()
    except:
        try:
            local_ip = socket.gethostbyname(socket.gethostname())
        except:
            pass
            
    # Crear archivo de configuración cnf temporal con Subject Alternative Names (SAN)
    # Requerido de forma obligatoria por los navegadores móviles para permitir getUserMedia (Cámara)
    san_list = f"DNS:localhost,IP:127.0.0.1,IP:{local_ip}"
    cnf_content = f"""[req]
default_bits       = 2048
prompt             = no
default_md         = sha256
distinguished_name = dn
x509_extensions    = v3_req

[dn]
C  = CO
ST = Colombia
L  = Bogota
O  = UNAL ProyectoOPCUA
OU = Automatizacion Industrial
CN = localhost

[v3_req]
subjectAltName     = {san_list}
keyUsage           = critical, digitalSignature, keyEncipherment
extendedKeyUsage   = serverAuth
basicConstraints   = CA:FALSE
"""
    cnf_file = "certs/openssl_temp.cnf"
    with open(cnf_file, "w") as f:
        f.write(cnf_content)
        
    try:
        cmd = [
            openssl_path, "req", "-x509",
            "-newkey", "rsa:2048",
            "-keyout", key_file,
            "-out", cert_file,
            "-sha256",
            "-days", "3650",
            "-nodes",
            "-config", cnf_file
        ]
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        log_success(f"Certificados SSL/TLS autofirmados generados con éxito.")
        log_success(f"SANs incluidos: {san_list}")
    except Exception as e:
        log_err(f"Fallo al ejecutar OpenSSL en Windows: {e}")
        log_warn("No se pudo autogenerar el certificado. Por favor, copia 'cert.pem' y 'key.pem' manualmente a 'certs/'.")
    finally:
        if os.path.exists(cnf_file):
            try: os.remove(cnf_file)
            except: pass

# ========================================================================
# INICIAR EL SERVIDOR WEB HTTPS
# ========================================================================
def start_web_server():
    server_address = ('', 8443)  # Servir en puerto 8443 (HTTPS oficial del proyecto C++)
    httpd = HTTPServer(server_address, IndustrialApiHandler)
    
    cert_file = "certs/cert.pem"
    key_file = "certs/key.pem"
    
    # Generar certificados si hacen falta
    generate_certificates_windows(cert_file, key_file)
    
    if os.path.exists(cert_file) and os.path.exists(key_file):
        try:
            # Envolver el socket usando ssl nativo de Python para exigir HTTPS de forma estricta
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            context.load_cert_chain(certfile=cert_file, keyfile=key_file)
            httpd.socket = context.wrap_socket(httpd.socket, server_side=True)
            log_success("Servidor seguro HTTPS iniciado en puerto 8443.")
        except Exception as e:
            log_err(f"Fallo al aplicar cifrado SSL al servidor: {e}")
            log_warn("Iniciando fallback a HTTP estándar en puerto 8080...")
            httpd.server_close()
            # Fallback a HTTP si falla radicalmente el wrapper
            httpd = HTTPServer(('', 8080), IndustrialApiHandler)
            log_success("Servidor HTTP (fallback) levantado en puerto 8080.")
            log_info(f"Dashboard Web disponible en: {GREEN}http://localhost:8080{RESET}")
            httpd.serve_forever()
            return
    else:
        log_err("Imposible iniciar modo HTTPS (Certificados no disponibles). Usando HTTP en puerto 8080.")
        httpd.server_close()
        httpd = HTTPServer(('', 8080), IndustrialApiHandler)
        httpd.serve_forever()
        return

    # Obtener IP local para mostrar URLs
    local_ip = "127.0.0.1"
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        s.close()
    except:
        try: local_ip = socket.gethostbyname(socket.gethostname())
        except: pass

    log_info(f"Dashboard Web HTTPS disponible en: {GREEN}https://localhost:8443{RESET}")
    log_info(f"Cámara móvil disponible en:      {GREEN}https://{local_ip}:8443{RESET}")
    log_warn("NOTA: Debes aceptar el certificado autofirmado en el navegador (Configuración Avanzada -> Continuar).")
    
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    log_warn("Deteniendo servidor web...")
    httpd.server_close()

# ========================================================================
# FLUJO PRINCIPAL E INTERFAZ CLI
# ========================================================================
if __name__ == "__main__":
    # Limpiar consola de entrada
    os.system('cls' if os.name == 'nt' else 'clear')
    
    print(f"{CYAN}========================================================================{RESET}")
    print(f"{CYAN}     MONITOR INDUSTRIAL & SIMULADOR OPC-UA (WINDOWS RUNTIME v1.0)       {RESET}")
    print(f"{CYAN}========================================================================{RESET}")
    print(f" Adaptado para: {WHITE}Raspberry Pi 3 Model B (HTTPS estricto habilitado){RESET}")
    print("")
    
    # 1. Base de datos
    init_database()
    sync_opc_config()
    state.sync_from_db()
    
    # 2. Arrancar Hilo de Servidor Web (REST API + Archivos Estáticos)
    web_thread = threading.Thread(target=start_web_server)
    web_thread.daemon = True
    web_thread.start()
    
    # 3. Arrancar Hilo de Simulación Dinámica de la Banda
    sim_thread = threading.Thread(target=band_simulation_loop)
    sim_thread.daemon = True
    sim_thread.start()
    
    # Simular arranque inicial del OPC UA
    time.sleep(0.5)
    log_success(f"Conexión OPC-UA establecida exitosamente con {state.opc_endpoint}")
    log_info("Consola en modo lectura de puerto Ethernet. Monitoreando tráfico...")
    print(f"{CYAN}------------------------------------------------------------------------{RESET}")
    print(f" Comandos de Consola:")
    print(f"   {GREEN}[1]{RESET} Simular Caja Categoría 1 (Pistón 1 en 2s)")
    print(f"   {GREEN}[2]{RESET} Simular Caja Categoría 2 (Pistón 2 en 4s)")
    print(f"   {GREEN}[3]{RESET} Simular Caja Categoría 3 (Dejar pasar)")
    print(f"   {GREEN}[x]{RESET} Simular Caja Inválida")
    print(f"   {GREEN}[s]{RESET} Ver estado resumido de variables")
    print(f"   {GREEN}[q]{RESET} Detener programa y salir")
    print(f"{CYAN}------------------------------------------------------------------------{RESET}")
    print("")
    
    # Bucle interactivo
    while True:
        try:
            cmd = input(f"{WHITE}Consola > {RESET}").strip().lower()
            if cmd == "q" or cmd == "salir" or cmd == "exit":
                log_warn("Cerrando simulador industrial...")
                break
            elif cmd == "1":
                log_info("Comando manual: Inyectando QR '1'...")
                process_qr_fsm("1")
            elif cmd == "2":
                log_info("Comando manual: Inyectando QR '2'...")
                process_qr_fsm("2")
            elif cmd == "3":
                log_info("Comando manual: Inyectando QR '3'...")
                process_qr_fsm("3")
            elif cmd == "x":
                log_info("Comando manual: Inyectando QR 'ERROR_BOX_123'...")
                process_qr_fsm("ERROR_BOX_123")
            elif cmd == "s" or cmd == "status":
                with state.lock:
                    print(f"\n{YELLOW}--- ESTADO DE VARIABLES PLC EN TIEMPO REAL ---{RESET}")
                    print(f"  Motor Principal : [{'EN MARCHA' if state.motor_running else 'DETENIDO'}]")
                    print(f"  Velocidad       : {state.motor_speed:.1f} RPM")
                    print(f"  Pistón 1 (Cat 1): [{'ACTIVO' if state.piston1_active else 'INACTIVO'}]")
                    print(f"  Pistón 2 (Cat 2): [{'ACTIVO' if state.piston2_active else 'INACTIVO'}]")
                    print(f"  FSM Estado      : {state.fsm_state}")
                    print(f"  Cajas Totales   : {state.total_classified} (Cat1: {state.count_cat1}, Cat2: {state.count_cat2}, Cat3: {state.count_cat3}, Otro: {state.count_otro})")
                    print(f"{YELLOW}---------------------------------------------{RESET}\n")
            else:
                if cmd:
                    log_warn(f"Comando '{cmd}' no reconocido. Usa 1, 2, 3, x, s, q.")
        except KeyboardInterrupt:
            break
            
    print(f"\n{CYAN}[MAIN] Simulador industrial apagado de forma segura.{RESET}")
