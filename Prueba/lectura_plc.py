import asyncio
import os
import json
import sys
from asyncua import Client, ua

URL = "opc.tcp://192.168.0.1:4840"

NODOS = {
    "piston1": "ns=4;i=2",
    "piston2": "ns=4;i=5",
    "motor_state": "ns=4;i=3",
    "motor_speed": "ns=4;i=4",
}

TYPES = {
    "piston1": "Boolean",
    "piston2": "Boolean",
    "motor_state": "Boolean",
    "motor_speed": "Int16",
}

DESCRIPTIONS = {
    "piston1": "Piston 1 status (True=Active, False=Inactive)",
    "piston2": "Piston 2 status (True=Active, False=Inactive)",
    "motor_state": "Motor state (True=On, False=Off)",
    "motor_speed": "Motor speed (RPM or value)",
}


async def browse_recursive(node, client, mapping, visited=None):
    if visited is None:
        visited = set()
    
    node_id_str = node.nodeid.to_string()
    if node_id_str in visited:
        return
    visited.add(node_id_str)
    
    try:
        children = await node.get_children()
    except Exception:
        return
        
    for child in children:
        try:
            node_class = await child.read_node_class()
        except Exception:
            continue
            
        if node_class == ua.NodeClass.Variable:
            # Skip standard OPC UA system variables in Namespace 0
            if child.nodeid.NamespaceIndex == 0:
                continue
            try:
                browse_name = (await child.read_browse_name()).Name
                value = await child.read_value()
                dt_node = client.get_node(await child.read_data_type())
                dt_name = (await dt_node.read_browse_name()).Name
                if dt_name == "Real":
                    dt_name = "Float"
                
                dt_lower = dt_name.lower()
                if "bool" in dt_lower:
                    cast_val = bool(value)
                elif "float" in dt_lower or "double" in dt_lower or "real" in dt_lower:
                    cast_val = float(value)
                elif "int" in dt_lower or "byte" in dt_lower or "word" in dt_lower or "uword" in dt_lower or "dword" in dt_lower:
                    cast_val = int(value)
                elif "string" in dt_lower:
                    cast_val = str(value)
                else:
                    cast_val = value
                
                try:
                    desc_node = await child.read_description()
                    if desc_node is None:
                        description = ""
                    elif hasattr(desc_node, "Text") and desc_node.Text is not None:
                        description = str(desc_node.Text)
                    else:
                        description = str(desc_node)
                except Exception:
                    description = ""
                
                child_id_str = child.nodeid.to_string()
                
                # Check if this node_id is already in the mapping (e.g. under standard keys)
                existing_key = None
                for k, v in mapping.items():
                    if isinstance(v, dict) and v.get("node_id") == child_id_str:
                        existing_key = k
                        break
                
                target_key = existing_key if existing_key else browse_name
                
                mapping[target_key] = {
                    "node_id": child_id_str,
                    "type": dt_name,
                    "value": cast_val,
                    "description": description
                }
            except Exception:
                pass
        elif node_class == ua.NodeClass.Object:
            # Avoid traversing the standard Server diagnostics node
            try:
                bn = await child.read_browse_name()
                if bn.Name == "Server":
                    continue
            except Exception:
                continue
            await browse_recursive(child, client, mapping, visited)
def sanitize_for_json(obj):
    if isinstance(obj, dict):
        return {k: sanitize_for_json(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [sanitize_for_json(x) for x in obj]
    elif isinstance(obj, (str, int, float, bool)) or obj is None:
        return obj
    elif hasattr(obj, "Text"):
        return str(obj.Text)
    elif hasattr(obj, "Name"):
        return str(obj.Name)
    else:
        return str(obj)


async def leer_estado():
    print(f"Conectando al servidor OPC UA en {URL}...")
    try:
        async with Client(url=URL) as client:
            print("¡Conectado exitosamente al S7-1200!\n")

            # 2. Pre-populate mapping with the default nodes as fallback/seed
            mapping = {}
            for key in ["piston1", "piston2", "motor_state", "motor_speed"]:
                node_id = NODOS[key]
                node_type = TYPES[key]
                description = DESCRIPTIONS[key]
                # Default fallback value
                val = False if node_type == "Boolean" else 0
                try:
                    node = client.get_node(node_id)
                    raw_val = await node.read_value()
                    if node_type == "Boolean":
                        val = bool(raw_val)
                    else:
                        val = int(raw_val)
                except Exception:
                    pass
                mapping[key] = {
                    "node_id": node_id,
                    "type": node_type,
                    "value": val,
                    "description": description
                }

            # 3. Discover and merge other nodes
            objects_node = client.get_objects_node()
            await browse_recursive(objects_node, client, mapping)

            # 4. Export the final mapping to plc_mapping.json
            export_data = {
                "url": URL,
                **mapping
            }
            script_dir = os.path.dirname(os.path.abspath(__file__))
            json_path = os.path.join(script_dir, "plc_mapping.json")
            sanitized_data = sanitize_for_json(export_data)
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(sanitized_data, f, indent=2)

            # 5. Print formatted table
            print("--- ESTADO ACTUAL DEL PLC ---")
            print(f"{'Variable':<20} | {'Node ID':<15} | {'Type':<10} | {'Value':<15} | {'Description'}")
            print("-" * 80)
            for name, info in mapping.items():
                val_str = str(info['value'])
                print(f"{name:<20} | {info['node_id']:<15} | {info['type']:<10} | {val_str:<15} | {info['description']}")

            return mapping

    except Exception as e:
        print(f"Error de conexión al PLC: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(leer_estado())

