import asyncio
import json
import logging
from datetime import datetime
from collections import deque
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import uvicorn
from asyncua import Server, ua

# ─── Estado global compartido ────────────────────────────────────────────────
state = {
    "running": False,
    "endpoint": "",
    "variables": {
        "Temperatura": 25.0,
        "Presion": 100,
        "Motor_Encendido": 0,
        "Categoria_QR": 0,
        "Confirmacion_QR": False,
    },
    "logs": deque(maxlen=120),
    "nodos": {},
    "server": None,
    "task": None,
}

def log(msg: str, level: str = "INFO"):
    ts = datetime.now().strftime("%H:%M:%S")
    state["logs"].append({"time": ts, "level": level, "msg": msg})
    print(f"[{ts}] [{level}] {msg}")

# ─── Servidor OPC UA (corre en background) ───────────────────────────────────
async def run_opcua(ip: str, port: int):
    try:
        server = Server()
        server.set_endpoint(f"opc.tcp://0.0.0.0:{port}/freeopcua/server/")
        server.set_server_name("Simulador PLC Web")
        server.set_security_policy([ua.SecurityPolicyType.NoSecurity])
        await server.init()

        uri = "http://unal.edu.co/automatizacion"
        idx = await server.register_namespace(uri)
        obj = await server.nodes.objects.add_object(idx, "PLC_Simulado")

        nodos = {
            "Temperatura":     await obj.add_variable(f"ns={idx};s=Temperatura",     "Temperatura",     25.0),
            "Presion":         await obj.add_variable(f"ns={idx};s=Presion",         "Presion",         100),
            "Motor_Encendido": await obj.add_variable(f"ns={idx};s=Motor_Encendido", "Motor_Encendido", 0),
            "Categoria_QR":    await obj.add_variable(f"ns={idx};s=Categoria_QR",    "Categoria_QR",    0),
            "Confirmacion_QR": await obj.add_variable(f"ns={idx};s=Confirmacion_QR", "Confirmacion_QR", False),
        }
        for n in nodos.values():
            await n.set_writable()

        state["nodos"] = nodos
        state["server"] = server
        state["endpoint"] = f"opc.tcp://{ip}:{port}/freeopcua/server/"
        state["running"] = True
        log(f"Servidor OPC UA levantado en {state['endpoint']}")
        log(f"  -> IP PLC: {ip}  | Puerto: {port}")

        vals_ant = {k: None for k in nodos}
        for k, n in nodos.items():
            vals_ant[k] = await n.read_value()

        async with server:
            while True:
                await asyncio.sleep(0.1)

                # Detectar cambios desde cliente externo (Raspberry Pi)
                for k, n in nodos.items():
                    v = await n.read_value()
                    if v != vals_ant[k]:
                        if k == "Motor_Encendido":
                            log(f"[RECIBIDO] Motor → {'ENCENDIDO' if v==1 else 'APAGADO'}")
                        elif k == "Categoria_QR" and v > 0:
                            log(f"[QR] Categoría recibida: {v}")
                            await nodos["Confirmacion_QR"].write_value(True)
                            await nodos["Categoria_QR"].write_value(0)
                            v = 0
                        else:
                            log(f"[RECIBIDO] {k} = {v}")
                        vals_ant[k] = v
                        state["variables"][k] = v

                # Sincronizar variables con el estado web
                for k, n in nodos.items():
                    state["variables"][k] = await n.read_value()

                # Simulación física: si el motor está on, sube la temperatura
                if await nodos["Motor_Encendido"].read_value() == 1:
                    t = await nodos["Temperatura"].read_value()
                    t = round(t + 0.5, 1)
                    if t > 80:
                        t = 25.0
                    await nodos["Temperatura"].write_value(t)
                    state["variables"]["Temperatura"] = t

    except asyncio.CancelledError:
        log("Servidor detenido.")
    except Exception as e:
        log(f"Error en servidor OPC UA: {e}", "ERROR")
    finally:
        state["running"] = False
        state["nodos"] = {}
        state["server"] = None

# ─── FastAPI ──────────────────────────────────────────────────────────────────
app = FastAPI(title="Simulador PLC Web")
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/", response_class=HTMLResponse)
async def index():
    with open("static/index.html", encoding="utf-8") as f:
        return f.read()

@app.get("/api/estado")
async def estado():
    return {
        "running": state["running"],
        "endpoint": state["endpoint"],
        "variables": {k: v for k, v in state["variables"].items()},
        "logs": list(state["logs"]),
    }

class StartRequest(BaseModel):
    ip: str = "192.168.10.11"
    port: int = 4845

@app.post("/api/iniciar")
async def iniciar(req: StartRequest):
    if state["running"]:
        return {"status": "error", "msg": "El servidor ya está corriendo."}
    task = asyncio.create_task(run_opcua(req.ip, req.port))
    state["task"] = task
    log(f"Iniciando servidor en {req.ip}:{req.port}...")
    return {"status": "ok", "msg": f"Iniciando en {req.ip}:{req.port}"}

@app.post("/api/detener")
async def detener():
    if state["task"]:
        state["task"].cancel()
        state["task"] = None
    state["running"] = False
    log("Servidor detenido por el usuario.")
    return {"status": "ok"}

class VarRequest(BaseModel):
    nombre: str
    valor: str

@app.post("/api/variable")
async def set_variable(req: VarRequest):
    if not state["running"] or not state["nodos"]:
        return {"status": "error", "msg": "Servidor no activo."}
    nodo = state["nodos"].get(req.nombre)
    if not nodo:
        return {"status": "error", "msg": "Variable no encontrada."}
    try:
        if req.nombre == "Temperatura":
            val = float(req.valor)
        elif req.nombre == "Confirmacion_QR":
            val = bool(int(req.valor))
        else:
            val = int(req.valor)
        await nodo.write_value(val)
        state["variables"][req.nombre] = val
        log(f"[FORZADO] {req.nombre} = {val}")
        return {"status": "ok"}
    except ValueError:
        return {"status": "error", "msg": "Valor inválido."}

if __name__ == "__main__":
    uvicorn.run("simulador_web:app", host="0.0.0.0", port=8000, reload=False)
