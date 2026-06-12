import asyncio
import sys
from asyncua import Client, ua

async def test_node(client, name, node_id):
    print(f"\n--- Probando {name} ({node_id}) ---")
    try:
        node = client.get_node(node_id)
        
        # Read initial state
        initial_val = await node.read_value()
        print(f"[{name}] Valor inicial: {initial_val}")
        
        # Write True
        print(f"[{name}] Escribiendo True...")
        dv_true = ua.DataValue(ua.Variant(True, ua.VariantType.Boolean))
        await node.write_value(dv_true)
        
        # Read back
        val_true = await node.read_value()
        print(f"[{name}] Valor leido (esperado True): {val_true}")
        if val_true is True:
            print(f"[{name}] OK: Escritura de True exitosa!")
        else:
            print(f"[{name}] ERROR: No cambio a True!")
            
        print(f"[{name}] Esperando 2 segundos...")
        await asyncio.sleep(2)
        
        # Write False
        print(f"[{name}] Escribiendo False...")
        dv_false = ua.DataValue(ua.Variant(False, ua.VariantType.Boolean))
        await node.write_value(dv_false)
        
        # Read back
        val_false = await node.read_value()
        print(f"[{name}] Valor leido (esperado False): {val_false}")
        if val_false is False:
            print(f"[{name}] OK: Escritura de False exitosa!")
        else:
            print(f"[{name}] ERROR: No cambio a False!")
            
    except Exception as e:
        print(f"[{name}] ERROR en la prueba: {e}")

async def main():
    url = "opc.tcp://192.168.0.1:4840"
    if len(sys.argv) > 1:
        url = sys.argv[1]
        
    print(f"Conectando al PLC en {url}...")
    client = Client(url=url)
    try:
        await client.connect()
        print("Conectado con exito!")
        
        # Test Categoria1, Categoria2, Categoria3
        await test_node(client, "Categoria1", "ns=4;i=8")
        await test_node(client, "Categoria2", "ns=4;i=7")
        await test_node(client, "Categoria3", "ns=4;i=6")
        
    except Exception as e:
        print(f"ERROR al conectar al PLC: {e}")
    finally:
        try:
            await client.disconnect()
        except:
            pass
        print("Desconectado.")

if __name__ == "__main__":
    asyncio.run(main())
