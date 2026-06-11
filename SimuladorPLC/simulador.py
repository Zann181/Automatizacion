import asyncio
import logging
import socket
import tkinter as tk
from tkinter import scrolledtext, ttk
from asyncua import Server, ua

# Función para obtener la IP real de la computadora en la red local
def obtener_ip_local():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "0.0.0.0"

# --- Configuración de la Interfaz Gráfica Tkinter ---
class TerminalGUI:
    def __init__(self, root, command_queue, start_callback):
        self.root = root
        self.command_queue = command_queue
        self.start_callback = start_callback
        self.root.title("Terminal OPC UA - PLC Simulado")
        self.root.geometry("800x650")
        self.root.configure(bg="black")

        # ----- PANEL SUPERIOR (CONFIGURACIÓN DE RED) -----
        top_frame = tk.Frame(root, bg="#333333")
        top_frame.pack(fill='x', padx=10, pady=(10, 5))

        tk.Label(top_frame, text="Mi IP Local:", bg="#333333", fg="white", font=("Consolas", 10, "bold")).pack(side=tk.LEFT, padx=5, pady=8)
        
        ip_real = "192.168.10.11"  # IP Fija Industrial por defecto (Ethernet directa)
        self.ip_entry = tk.Entry(top_frame, width=15, font=("Consolas", 10))
        self.ip_entry.insert(0, ip_real)
        self.ip_entry.pack(side=tk.LEFT, padx=5)

        tk.Label(top_frame, text="Puerto:", bg="#333333", fg="white", font=("Consolas", 10)).pack(side=tk.LEFT, padx=5)
        self.port_entry = tk.Entry(top_frame, width=8, font=("Consolas", 10))
        self.port_entry.insert(0, "4845")
        self.port_entry.pack(side=tk.LEFT, padx=5)

        self.start_btn = tk.Button(top_frame, text="INICIAR SERVIDOR", bg="#0088FF", fg="white", font=("Consolas", 10, "bold"), command=self.on_start)
        self.start_btn.pack(side=tk.LEFT, padx=15)

        # Texto con estilo "Hacker"
        self.text_area = scrolledtext.ScrolledText(
            root, wrap=tk.WORD, bg="black", fg="#00FF00", 
            font=("Consolas", 11), insertbackground="white"
        )
        self.text_area.pack(expand=True, fill='both', padx=10, pady=5)
        self.text_area.insert(tk.END, "=== SIMULADOR DE PLC INDUSTRIAL ===\n")
        self.text_area.configure(state='disabled')

        # ----- PANEL DE CONTROLES INFERIOR (ENVIAR) -----
        control_frame = tk.Frame(root, bg="#222222")
        control_frame.pack(fill='x', padx=10, pady=(0, 10))

        tk.Label(control_frame, text="Modificar Variable:", bg="#222222", fg="white", font=("Consolas", 10)).pack(side=tk.LEFT, padx=5, pady=8)
        
        # Agregadas las variables del QR al combo
        self.var_combo = ttk.Combobox(control_frame, values=["Temperatura", "Presion", "Motor_Encendido", "Confirmacion_QR"], state="readonly", width=17)
        self.var_combo.current(0)
        self.var_combo.pack(side=tk.LEFT, padx=5)

        tk.Label(control_frame, text="Nuevo Valor:", bg="#222222", fg="white", font=("Consolas", 10)).pack(side=tk.LEFT, padx=5)
        
        self.val_entry = tk.Entry(control_frame, width=10, font=("Consolas", 10))
        self.val_entry.pack(side=tk.LEFT, padx=5)
        self.val_entry.bind('<Return>', lambda event: self.enviar_comando()) 

        self.send_btn = tk.Button(control_frame, text="ENVIAR", bg="#00FF00", fg="black", font=("Consolas", 10, "bold"), command=self.enviar_comando)
        self.send_btn.pack(side=tk.LEFT, padx=10)
        
        self.send_btn.configure(state=tk.DISABLED)

    def on_start(self):
        ip = self.ip_entry.get().strip()
        port = self.port_entry.get().strip()
        if ip and port:
            self.ip_entry.configure(state='disabled')
            self.port_entry.configure(state='disabled')
            self.start_btn.configure(state='disabled')
            self.send_btn.configure(state='normal')
            self.start_callback(ip, port)

    def reset_ui_on_error(self):
        self.ip_entry.configure(state='normal')
        self.port_entry.configure(state='normal')
        self.start_btn.configure(state='normal')
        self.send_btn.configure(state='disabled')

    def enviar_comando(self):
        if str(self.send_btn['state']) == 'disabled': return
        variable = self.var_combo.get()
        valor = self.val_entry.get()
        if valor:
            self.command_queue.put_nowait((variable, valor))
            self.log(f"\n[CONSOLA LOCAL] Has ordenado cambiar {variable} a {valor}...")
            self.val_entry.delete(0, tk.END)

    def log(self, message):
        self.text_area.configure(state='normal')
        self.text_area.insert(tk.END, message + "\n")
        self.text_area.configure(state='disabled')
        self.text_area.yview(tk.END)

# --- Redirigir eventos a la Interfaz ---
class TkinterHandler(logging.Handler):
    def __init__(self, gui):
        super().__init__()
        self.gui = gui

    def emit(self, record):
        msg = self.format(record)
        if "Listening" in msg or "New connection" in msg or "Connection closed" in msg:
            self.gui.log(f"[RED] {msg}")

# --- Ciclo Principal del Servidor OPC UA ---
async def main():
    command_queue = asyncio.Queue()
    start_queue = asyncio.Queue()

    def start_cb(ip, port):
        start_queue.put_nowait((ip, port))

    root = tk.Tk()
    gui = TerminalGUI(root, command_queue, start_cb)

    logger = logging.getLogger('asyncua.server.uaprocessor')
    logger.setLevel(logging.INFO)
    tk_handler = TkinterHandler(gui)
    tk_handler.setFormatter(logging.Formatter('%(message)s'))
    logger.addHandler(tk_handler)

    gui.log("¡Bienvenido! Haz clic en 'INICIAR SERVIDOR' para comenzar.")

    while True:
        while True:
            try:
                root.update()
            except tk.TclError:
                return

            if not start_queue.empty():
                ip, port = start_queue.get_nowait()
                break
            await asyncio.sleep(0.05)

        try:
            gui.log(f"\n[INFO] Inicializando servidor en la IP {ip} ...")
            server = Server()
            server.set_endpoint(f"opc.tcp://0.0.0.0:{port}/freeopcua/server/")  # 0.0.0.0 = escucha en todas las interfaces
            server.set_server_name("Simulador PLC GUI")
            server.set_security_policy([ua.SecurityPolicyType.NoSecurity])
            await server.init()

            uri = "http://unal.edu.co/automatizacion"
            idx = await server.register_namespace(uri)

            myobj = await server.nodes.objects.add_object(idx, "PLC_Simulado")

            nodos = {
                "Temperatura": await myobj.add_variable(f"ns={idx};s=Temperatura", "Temperatura", 25.0),
                "Presion": await myobj.add_variable(f"ns={idx};s=Presion", "Presion", 100),
                "Motor_Encendido": await myobj.add_variable(f"ns={idx};s=Motor_Encendido", "Motor_Encendido", 0),
                "Categoria_QR": await myobj.add_variable(f"ns={idx};s=Categoria_QR", "Categoria_QR", 0),           
                "Confirmacion_QR": await myobj.add_variable(f"ns={idx};s=Confirmacion_QR", "Confirmacion_QR", False) 
            }

            for nodo in nodos.values():
                await nodo.set_writable()

            gui.log(f"[INFO] Servidor levantado correctamente.")
            gui.log(f"   -> EN LA INTERFAZ WEB DE LA RASPBERRY PI PON ESTA IP:")
            gui.log(f"   -> IP PLC: {ip}  | Puerto: {port}\n")
            
            valores_ant = {k: None for k in nodos}

            async with server:
                for k, v in nodos.items():
                    valores_ant[k] = await v.read_value()

                while True:
                    try:
                        root.update() 
                    except tk.TclError:
                        return 

                    await asyncio.sleep(0.05) 
                    
                    # 1. FORZAR DATOS DESDE LA GUI (Ej: resetear Confirmacion_QR)
                    while not command_queue.empty():
                        var_name, val_str = command_queue.get_nowait()
                        if var_name in nodos:
                            try:
                                if var_name == "Motor_Encendido": val = 1 if int(val_str) > 0 else 0
                                elif var_name == "Confirmacion_QR": val = bool(int(val_str))
                                elif var_name == "Temperatura": val = float(val_str)
                                else: val = int(val_str)
                                    
                                await nodos[var_name].write_value(val)
                                gui.log(f"[MANDANDO] Has forzado el valor de {var_name} a {val}")
                                valores_ant[var_name] = val 
                            except ValueError:
                                gui.log(f"[ERROR LOCAL] El valor '{val_str}' debe ser un número.")

                    # 2. DETECTAR LO QUE RECIBE DEL CLIENTE (RASPBERRY)
                    for k, nodo in nodos.items():
                        val_actual = await nodo.read_value()
                        if val_actual != valores_ant[k]:
                            if k == "Motor_Encendido":
                                estado = "ENCENDIDO" if val_actual == 1 else "APAGADO"
                                gui.log(f"[RECIBIDO] La Raspberry Pi ordenó: Motor {estado}")
                            elif k == "Categoria_QR":
                                if val_actual > 0:
                                    gui.log(f"\n[QR DETECTADO] ===== ¡NUEVO ESCANEO! =====")
                                    gui.log(f"[QR DETECTADO] La Raspberry Pi envió la Categoría QR: {val_actual}")
                                    
                                    # ENVIAR CONFIRMACIÓN DE VUELTA
                                    await nodos["Confirmacion_QR"].write_value(True)
                                    gui.log(f"[MANDANDO] ¡Enviando señal de confirmación de QR a la Raspberry!")
                                    valores_ant["Confirmacion_QR"] = True
                                    
                                    # Limpiar la categoría para el próximo escaneo
                                    await nodos["Categoria_QR"].write_value(0)
                                    val_actual = 0 # Prevenir que el siguiente if lo atrape
                                    gui.log(f"[SISTEMA] Categoría QR reseteada internamente a 0 para próximos escaneos.\n")
                            else:
                                gui.log(f"[RECIBIDO] La Raspberry Pi ajustó {k} a {val_actual}")
                            
                            valores_ant[k] = val_actual

                    # 3. SIMULACIÓN FÍSICA
                    motor_actual = await nodos["Motor_Encendido"].read_value()
                    if motor_actual == 1:
                        temp_actual = await nodos["Temperatura"].read_value()
                        temp_actual += 0.5
                        if temp_actual > 80: temp_actual = 25.0
                            
                        await nodos["Temperatura"].write_value(temp_actual)
                        valores_ant["Temperatura"] = temp_actual 
                        if int(temp_actual) != int(valores_ant["Temperatura"] - 0.5):
                            gui.log(f"[MANDANDO] Temperatura subiendo: {temp_actual:.1f}°C")

        except Exception as e:
            gui.log(f"\n[ERROR DE RED] No se pudo iniciar el servidor.")
            gui.log(f"Detalle técnico: {e}")
            gui.reset_ui_on_error()

if __name__ == "__main__":
    asyncio.run(main())
