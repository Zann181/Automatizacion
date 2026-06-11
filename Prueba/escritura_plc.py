import asyncio
import os
import json
import sys
from asyncua import Client, ua

# Get path of plc_mapping.json
script_dir = os.path.dirname(os.path.abspath(__file__))
json_path = os.path.join(script_dir, "plc_mapping.json")

# 1. Load plc_mapping.json at startup.
if not os.path.exists(json_path):
    print("Error: El archivo 'plc_mapping.json' no existe.")
    print("Por favor, ejecute 'lectura_plc.py' primero para generar el mapeo de variables.")
    sys.exit(1)

try:
    with open(json_path, "r", encoding="utf-8") as f:
        mapping = json.load(f)
except Exception as e:
    print(f"Error al cargar 'plc_mapping.json': {e}")
    sys.exit(1)

# Extract URL
url = mapping.get("url", "opc.tcp://192.168.0.1:4840")


def parse_bool(val_str: str) -> bool:
    clean = val_str.strip().lower()
    if clean in ('true', '1', 'y', 'yes', 'si', 's', 'on', 'activo', 'active', 't'):
        return True
    elif clean in ('false', '0', 'n', 'no', 'off', 'inactivo', 'inactive', 'f'):
        return False
    else:
        raise ValueError(f"No se pudo parsear '{val_str}' como Booleano.")


async def refresh_values(client, mapping, json_path):
    for var_name, info in mapping.items():
        if var_name == "url":
            continue
        node_id = info["node_id"]
        var_type = info["type"]
        node = client.get_node(node_id)
        raw_val = await node.read_value()
        
        # Cast according to type
        if var_type == "Boolean":
            val = bool(raw_val)
        elif var_type in ("Int16", "Int32", "UInt16", "UInt32"):
            val = int(raw_val)
        elif var_type in ("Float", "Double"):
            val = float(raw_val)
        else:
            val = raw_val
        
        info["value"] = val
    
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(mapping, f, indent=2)


async def main():
    # 2. Connect to the OPC UA PLC using the URL from plc_mapping.json or from the script.
    # Handle connection exceptions gracefully.
    print(f"Conectando al servidor OPC UA en {url}...")
    client = Client(url=url)
    try:
        await client.connect()
        print("¡Conectado exitosamente al S7-1200!\n")
    except Exception as e:
        print(f"❌ Error de conexión al PLC: {e}")
        sys.exit(1)

    try:
        # Get variables list excluding "url"
        variables = [k for k in mapping.keys() if k != "url"]

        # 3. Interactive 'while True' terminal menu
        while True:
            print("\n==================================================")
            print("                MENU DE CONTROL PLC               ")
            print("==================================================")
            for i, var_name in enumerate(variables, 1):
                info = mapping[var_name]
                val = info.get("value")
                var_type = info.get("type")
                desc = info.get("description", "")
                print(f"[{i}] {var_name}")
                print(f"    Valor actual : {val}")
                print(f"    Tipo         : {var_type}")
                print(f"    Descripción  : {desc}")
                print("-" * 50)
            print("[R] Refresh/Reload (Recargar valores del PLC)")
            print("[Q] Quit (Salir)")
            print("==================================================")

            option_input = input(f"Seleccione una variable (1-{len(variables)}) o una opción (R/Q): ").strip().upper()

            if option_input == 'Q':
                print("Desconectando del PLC...")
                break

            elif option_input == 'R':
                try:
                    await refresh_values(client, mapping, json_path)
                    print("Valores actualizados desde el PLC.")
                except Exception as e:
                    print(f"❌ Error al recargar los valores del PLC: {e}")

            elif option_input.isdigit():
                idx = int(option_input)
                if 1 <= idx <= len(variables):
                    var_name = variables[idx - 1]
                    info = mapping[var_name]
                    var_type = info["type"]
                    node_id = info["node_id"]

                    # Prompt based on data type
                    if var_type == "Boolean":
                        value_input = input(f"Ingrese el nuevo valor para {var_name} (T/F): ")
                    elif var_type in ("Int16", "Int32", "UInt16", "UInt32"):
                        value_input = input(f"Ingrese un valor entero para {var_name}: ")
                    elif var_type in ("Float", "Double"):
                        value_input = input(f"Ingrese un valor decimal para {var_name}: ")
                    else:
                        value_input = input(f"Ingrese el nuevo valor para {var_name} ({var_type}): ")

                    # Parse input
                    try:
                        if var_type == "Boolean":
                            parsed_val = parse_bool(value_input)
                            variant_type = ua.VariantType.Boolean
                        elif var_type == "Int16":
                            parsed_val = int(value_input.strip())
                            variant_type = ua.VariantType.Int16
                        elif var_type == "Int32":
                            parsed_val = int(value_input.strip())
                            variant_type = ua.VariantType.Int32
                        elif var_type == "UInt16":
                            parsed_val = int(value_input.strip())
                            variant_type = ua.VariantType.UInt16
                        elif var_type == "UInt32":
                            parsed_val = int(value_input.strip())
                            variant_type = ua.VariantType.UInt32
                        elif var_type in ("Float", "Double"):
                            parsed_val = float(value_input.strip())
                            variant_type = ua.VariantType.Float
                        elif var_type == "String":
                            parsed_val = str(value_input)
                            variant_type = ua.VariantType.String
                        else:
                            # Generic fallback
                            parsed_val = value_input
                            variant_type = ua.VariantType.String
                    except ValueError as ve:
                        print(f"❌ ERROR de formato: {ve}")
                        continue

                    # Write value to PLC
                    try:
                        node = client.get_node(node_id)
                        dv = ua.DataValue(ua.Variant(parsed_val, variant_type))
                        await node.write_value(dv)
                        
                        # Wait a short moment
                        await asyncio.sleep(0.5)

                        # Read back value
                        read_back_raw = await node.read_value()
                        if var_type == "Boolean":
                            read_back_val = bool(read_back_raw)
                        elif var_type in ("Int16", "Int32", "UInt16", "UInt32"):
                            read_back_val = int(read_back_raw)
                        elif var_type in ("Float", "Double"):
                            read_back_val = float(read_back_raw)
                        else:
                            read_back_val = read_back_raw

                        # Verify if the read-back value matches
                        if read_back_val == parsed_val:
                            print("✅ ¡VERIFICADO! El PLC aplicó el cambio.")
                        else:
                            print("❌ ERROR: El cambio no se aplicó.")

                        # Update JSON in-memory and write back to file
                        info["value"] = read_back_val
                        with open(json_path, "w", encoding="utf-8") as f:
                            json.dump(mapping, f, indent=2)

                    except Exception as e:
                        print(f"❌ Error al escribir o verificar en el PLC: {e}")
                else:
                    print(f"❌ Opción no válida. Ingrese un número entre 1 y {len(variables)}, 'R' o 'Q'.")
            else:
                print("❌ Opción no válida. Ingrese un número (1-4), 'R' o 'Q'.")

    finally:
        await client.disconnect()
        print("Conexión cerrada.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nPrograma terminado por el usuario.")
