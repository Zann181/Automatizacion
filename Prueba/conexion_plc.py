import asyncio
from asyncua import Client, ua

# La dirección IP de tu PLC
URL = "opc.tcp://192.168.0.1:4840" 

async def main():
    print(f"Conectando al servidor OPC UA en {URL}...")
    async with Client(url=URL) as client:
        print("¡Conectado exitosamente al S7-1200!\n")

        # 1. ASIGNAMOS LOS NODOS EXACTOS SEGÚN TU ESCANEO
        nodo_piston1 = client.get_node("ns=4;i=2")
        nodo_piston2 = client.get_node("ns=4;i=5")

        nodo_motor_state = client.get_node("ns=4;i=3")
        nodo_motor_speed = client.get_node("ns=4;i=4")

        # 2. LEER EL ESTADO INICIAL DEL SISTEMA
        print("--- LEYENDO ESTADO ACTUAL ---")
        estado_piston = await nodo_piston1.read_value()
        estado_piston2 = await nodo_piston2.read_value()
        estado_motor = await nodo_motor_state.read_value()
        velocidad_motor = await nodo_motor_speed.read_value()
        
        print(f"Piston 1 está: {'Activo (True)' if estado_piston else 'Inactivo (False)'}")
        print(f"Piston 2 está: {'Activo (True)' if estado_piston2 else 'Inactivo (False)'}")
        print(f"Motor está: {'Encendido (True)' if estado_motor else 'Apagado (False)'}")
        print(f"Velocidad del motor: {velocidad_motor}\n")

        # 3. ENVIAR SEÑALES DE CONTROL CON EMPAQUETADO ESTRICTO
        print("--- ENVIANDO SEÑALES DE CONTROL AL PLC ---")
        
        # Invertimos el estado actual del pistón (de False a True, o de True a False)
        nuevo_estado = not estado_piston 
        print(f"Enviando orden al Piston 1: {nuevo_estado}...")
        
        # Empaquetado estricto para Siemens (Booleano)
        dv_piston = ua.DataValue(ua.Variant(nuevo_estado, ua.VariantType.Boolean))
        await nodo_piston1.write_value(dv_piston)

        # Invertimos el estado actual del pistón 2
        nuevo_estado2 = not estado_piston2
        print(f"Enviando orden al Piston 2: {nuevo_estado2}...")
        
        dv_piston2 = ua.DataValue(ua.Variant(nuevo_estado2, ua.VariantType.Boolean))
        await nodo_piston2.write_value(dv_piston2)

        # Enviamos una velocidad nueva al motor (Ejemplo: 1500)
        nueva_velocidad = 60        
        print(f"Enviando nueva velocidad al Motor: {nueva_velocidad}...")
        
        # Empaquetado estricto para Siemens (Entero de 16 bits)
        dv_velocidad = ua.DataValue(ua.Variant(nueva_velocidad, ua.VariantType.Int16))
        await nodo_motor_speed.write_value(dv_velocidad)

        # Damos un pequeño respiro de 1 segundo para que el PLC procese físicamente la señal
        await asyncio.sleep(1)

        # 4. VERIFICAR QUE LA SEÑAL LLEGÓ CORRECTAMENTE
        print("\n--- VERIFICANDO QUE LA SEÑAL LLEGÓ ---")
        verificacion_piston = await nodo_piston1.read_value()
        verificacion_piston2 = await nodo_piston2.read_value()
        verificacion_velocidad = await nodo_motor_speed.read_value()

        if verificacion_piston == nuevo_estado:
            print("✅ ¡VERIFICADO! El PLC recibió y aplicó el cambio en el Piston 1.")
        else:
            print("❌ ERROR: El cambio en el Piston 1 no se aplicó.")

        if verificacion_piston2 == nuevo_estado2:
            print("✅ ¡VERIFICADO! El PLC recibió y aplicó el cambio en el Piston 2.")
        else:
            print("❌ ERROR: El cambio en el Piston 2 no se aplicó.")

        if verificacion_velocidad == nueva_velocidad:
            print("✅ ¡VERIFICADO! El PLC recibió y aplicó la nueva velocidad del motor.")
        else:
            print("❌ ERROR: La velocidad del motor no cambió.")

if __name__ == "__main__":
    asyncio.run(main())