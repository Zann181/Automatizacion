#include <open62541/client.h>
#include <open62541/client_config.h>
#include <open62541/plugin/log_stdout.h>
#include <iostream>
#include <string>

int main() {
    // Dirección del PLC (igual al Python original)
    const std::string URL = "opc.tcp://192.168.0.1:4840";
    std::cout << "Conectando al servidor OPC UA en " << URL << "..." << std::endl;

    // Configuración estándar del cliente open62541
    UA_ClientConfig config = UA_ClientConfig_default;
    // Timeout de 5 s (5000 ms) – puede ajustarse si se define TIMEOUT_MS en python
    config.timeout = 5000;
    config.secureChannelLifeTime = 60000; // 1 min (valor razonable)

    UA_Client *client = UA_Client_new(config);
    if (!client) {
        std::cerr << "[ERROR] No se pudo crear el cliente UA" << std::endl;
        return EXIT_FAILURE;
    }

    UA_StatusCode retval = UA_Client_connect(client, URL.c_str());
    if (retval != UA_STATUSCODE_GOOD) {
        std::cerr << "[ERROR] No se pudo conectar: " << UA_StatusCode_name(retval) << std::endl;
        UA_Client_delete(client);
        return EXIT_FAILURE;
    }
    std::cout << "¡Conectado exitosamente al S7‑1200!" << std::endl;

    // Nodos a leer (ns=4;i=2, ns=4;i=5, ns=4;i=3, ns=4;i=4)
    UA_NodeId nodo_piston1 = UA_NODEID_NUMERIC(4, 2);
    UA_NodeId nodo_piston2 = UA_NODEID_NUMERIC(4, 5);
    UA_NodeId nodo_motor_state = UA_NODEID_NUMERIC(4, 3);
    UA_NodeId nodo_motor_speed = UA_NodeID_NUMERIC(4, 4);

    std::cout << "--- LEYENDO ESTADO ACTUAL ---" << std::endl;

    auto readAndPrint = [&](const UA_NodeId &node, const std::string &label) {
        UA_Variant value;
        UA_Variant_init(&value);
        UA_StatusCode rc = UA_Client_readValueAttribute(client, node, &value);
        if (rc == UA_STATUSCODE_GOOD) {
            // Intentamos imprimir los tipos más comunes (bool, int, float, double)
            if (UA_Variant_hasScalarType(&value, &UA_TYPES[UA_TYPES_BOOLEAN])) {
                bool v = *static_cast<bool*>(value.data);
                std::cout << label << " = " << (v ? "True" : "False") << std::endl;
            } else if (UA_Variant_hasScalarType(&value, &UA_TYPES[UA_TYPES_INT16])) {
                std::int16_t v = *static_cast<std::int16_t*>(value.data);
                std::cout << label << " = " << v << std::endl;
            } else if (UA_Variant_hasScalarType(&value, &UA_TYPES[UA_TYPES_INT32])) {
                std::int32_t v = *static_cast<std::int32_t*>(value.data);
                std::cout << label << " = " << v << std::endl;
            } else if (UA_Variant_hasScalarType(&value, &UA_TYPES[UA_TYPES_FLOAT])) {
                float v = *static_cast<float*>(value.data);
                std::cout << label << " = " << v << std::endl;
            } else if (UA_Variant_hasScalarType(&value, &UA_TYPES[UA_TYPES_DOUBLE])) {
                double v = *static_cast<double*>(value.data);
                std::cout << label << " = " << v << std::endl;
            } else {
                // Fallback: convertir a string mediante la API de open62541
                UA_String str = UA_Variant_toString(&value);
                std::cout << label << " = " << std::string(reinterpret_cast<char*>(str.data), str.length) << std::endl;
                UA_String_clear(&str);
            }
        } else {
            std::cerr << "[ERROR] No se pudo leer " << label << ": " << UA_StatusCode_name(rc) << std::endl;
        }
        UA_Variant_clear(&value);
    };

    readAndPrint(nodo_piston1, "Piston 1");
    readAndPrint(nodo_piston2, "Piston 2");
    readAndPrint(nodo_motor_state, "Motor State");
    readAndPrint(nodo_motor_speed, "Motor Speed");

    UA_Client_disconnect(client);
    UA_Client_delete(client);
    std::cout << "Cliente desconectado. Fin del programa." << std::endl;
    return EXIT_SUCCESS;
}
