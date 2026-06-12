import asyncio
from asyncua import Client, ua

async def main():
    url = "opc.tcp://192.168.0.1:4840"
    print(f"Conectando al PLC en {url}...")
    client = Client(url=url)
    try:
        await client.connect()
        print("Conectado con éxito!")
        
        node_id = "ns=4;i=7" # Categoria2
        node = client.get_node(node_id)
        
        # 1. Leer estado inicial
        val_inicial = await node.read_value()
        print(f"1. Estado inicial leido de {node_id}: {val_inicial}")
        
        # 2. Escribir True
        print(f"2. Escribiendo True a {node_id}...")
        dv_true = ua.DataValue(ua.Variant(True, ua.VariantType.Boolean))
        await node.write_value(dv_true)
        
        # 3. Leer inmediatamente para verificar
        val_verif_true = await node.read_value()
        print(f"3. Valor leido inmediatamente despues de escribir True: {val_verif_true}")
        if val_verif_true == True:
            print("✅ ¡EXITO! El PLC confirmo que el valor cambio a True.")
        else:
            print("❌ ERROR: El PLC devolvio False. La escritura no se aplico.")
            
        print("Esperando 2 segundos...")
        await asyncio.sleep(2)
        
        # 4. Escribir False
        print(f"4. Escribiendo False a {node_id}...")
        dv_false = ua.DataValue(ua.Variant(False, ua.VariantType.Boolean))
        await node.write_value(dv_false)
        
        # 5. Leer inmediatamente para verificar
        val_verif_false = await node.read_value()
        print(f"5. Valor leido inmediatamente despues de escribir False: {val_verif_false}")
        if val_verif_false == False:
            print("✅ ¡EXITO! El PLC confirmo que el valor volvio a False.")
        else:
            print("❌ ERROR: El PLC sigue en True.")
            
    except Exception as e:
        print(f"❌ ERROR durante la prueba: {e}")
    finally:
        try:
            await client.disconnect()
        except:
            pass
        print("Desconectado.")

if __name__ == "__main__":
    asyncio.run(main())
