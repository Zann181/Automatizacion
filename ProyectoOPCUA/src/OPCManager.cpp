#include "OPCManager.h"
#include <iostream>

static void dataChangeNotificationCallback(UA_Client *client, UA_UInt32 subId, void *subContext,
                                           UA_UInt32 monId, void *monContext, UA_DataValue *value) {
    (void)client;
    (void)subId;
    (void)subContext;
    (void)monId;
    (void)monContext;
    // Aquí el valor se notificaría al DatabaseManager para loggearlo, o a WebSockets.
    if(UA_Variant_hasScalarType(&value->value, &UA_TYPES[UA_TYPES_FLOAT])) {
        float val = *(float*)value->value.data;
        std::cout << "[OPCManager] Cambio detectado: " << val << std::endl;
    } else if (UA_Variant_hasScalarType(&value->value, &UA_TYPES[UA_TYPES_INT32])) {
        int32_t val = *(int32_t*)value->value.data;
        std::cout << "[OPCManager] Cambio detectado: " << val << std::endl;
    } else if (UA_Variant_hasScalarType(&value->value, &UA_TYPES[UA_TYPES_BOOLEAN])) {
        bool val = *(bool*)value->value.data;
        std::cout << "[OPCManager] Cambio detectado: " << (val ? "true" : "false") << std::endl;
    }
}

OPCManager::OPCManager() : is_connected(false), running(false) {
    client = UA_Client_new();
}

OPCManager::~OPCManager() {
    disconnect();
    UA_Client_delete(client);
}

bool OPCManager::connect(const std::string& endpoint, int timeout_ms) {
    std::lock_guard<std::mutex> lock(mtx);
    if (is_connected) return true;

    UA_ClientConfig *config = UA_Client_getConfig(client);
    UA_ClientConfig_setDefault(config);
    config->timeout = timeout_ms;

    UA_StatusCode retval = UA_Client_connect(client, endpoint.c_str());
    if(retval != UA_STATUSCODE_GOOD) {
        std::cerr << "[OPCManager] Error conectando a " << endpoint << std::endl;
        return false;
    }

    is_connected = true;
    running = true;
    
    client_thread = std::thread(&OPCManager::runClientLoop, this);
    std::cout << "[OPCManager] Conectado a " << endpoint << std::endl;
    return true;
}

void OPCManager::disconnect() {
    running = false;
    if (client_thread.joinable()) {
        client_thread.join();
    }
    
    std::lock_guard<std::mutex> lock(mtx);
    if (is_connected) {
        UA_Client_disconnect(client);
        is_connected = false;
        subscriptions.clear();
        std::cout << "[OPCManager] Desconectado." << std::endl;
    }
}

void OPCManager::runClientLoop() {
    while (running) {
        {
            std::lock_guard<std::mutex> lock(mtx);
            if (is_connected) {
                UA_Client_run_iterate(client, 0);
            }
        }
        std::this_thread::sleep_for(std::chrono::milliseconds(50));
    }
}

bool OPCManager::isConnected() const {
    if (!is_connected) return false;
    UA_SecureChannelState channelState = UA_SECURECHANNELSTATE_CLOSED;
    UA_SessionState sessionState = UA_SESSIONSTATE_CLOSED;
    UA_Client_getState(client, &channelState, &sessionState, nullptr);
    return (sessionState == UA_SESSIONSTATE_ACTIVATED);
}

bool OPCManager::subscribeVariable(const VariableOpc& var) {
    std::lock_guard<std::mutex> lock(mtx);
    if (!is_connected) return false;
    if (subscriptions.find(var.id) != subscriptions.end()) return true;

    UA_CreateSubscriptionRequest request = UA_CreateSubscriptionRequest_default();
    request.requestedPublishingInterval = var.scan_rate_ms;
    UA_CreateSubscriptionResponse response = UA_Client_Subscriptions_create(client, request, nullptr, nullptr, nullptr);
    if(response.responseHeader.serviceResult != UA_STATUSCODE_GOOD) return false;

    // Asumimos NodeId es un String, ej: s=Temperatura
    std::string pure_node = var.node_id;
    if (pure_node.substr(0, 2) == "s=") {
        pure_node = pure_node.substr(2);
    }
    
    UA_MonitoredItemCreateRequest monRequest = UA_MonitoredItemCreateRequest_default(
        UA_NODEID_STRING(var.ns_index, (char*)pure_node.c_str())
    );

    UA_MonitoredItemCreateResult monResponse = UA_Client_MonitoredItems_createDataChange(
        client, response.subscriptionId, UA_TIMESTAMPSTORETURN_BOTH, monRequest,
        nullptr, dataChangeNotificationCallback, nullptr);
        
    if(monResponse.statusCode != UA_STATUSCODE_GOOD) {
        return false;
    }

    SubInfo info;
    info.subId = response.subscriptionId;
    info.monId = monResponse.monitoredItemId;
    subscriptions[var.id] = info;

    std::cout << "[OPCManager] Suscrito a " << var.name << " (" << pure_node << ")" << std::endl;
    return true;
}

bool OPCManager::unsubscribeVariable(int var_id) {
    std::lock_guard<std::mutex> lock(mtx);
    if (!is_connected) return false;

    auto it = subscriptions.find(var_id);
    if (it == subscriptions.end()) return false;

    UA_Client_Subscriptions_deleteSingle(client, it->second.subId);
    subscriptions.erase(it);
    std::cout << "[OPCManager] Desuscrito de var_id: " << var_id << std::endl;
    return true;
}

bool OPCManager::writeVariable(const VariableOpc& var, const std::string& value) {
    std::lock_guard<std::mutex> lock(mtx);
    if (!is_connected) {
        std::cerr << "[OPCManager] Error: No conectado al servidor OPC UA para escribir '" << var.name << "'" << std::endl;
        return false;
    }
    if (!var.writable) {
        std::cerr << "[OPCManager] Error: Variable '" << var.name << "' no es de escritura." << std::endl;
        return false;
    }

    UA_Variant myVariant;
    UA_Variant_init(&myVariant);

    if (var.data_type == "Float") {
        UA_Float val = std::stof(value);
        UA_Variant_setScalarCopy(&myVariant, &val, &UA_TYPES[UA_TYPES_FLOAT]);
    } else if (var.data_type == "Int32") {
        UA_Int32 val = std::stoi(value);
        UA_Variant_setScalarCopy(&myVariant, &val, &UA_TYPES[UA_TYPES_INT32]);
    } else if (var.data_type == "Boolean") {
        UA_Boolean val = (value == "1" || value == "true") ? true : false;
        UA_Variant_setScalarCopy(&myVariant, &val, &UA_TYPES[UA_TYPES_BOOLEAN]);
    } else {
        std::cerr << "[OPCManager] Error: Tipo de dato '" << var.data_type << "' no soportado." << std::endl;
        return false;
    }

    std::string pure_node = var.node_id;
    if (pure_node.substr(0, 2) == "s=") pure_node = pure_node.substr(2);

    std::cout << "[OPCManager] ESCRIBIENDO -> ns=" << var.ns_index 
              << ";s=\"" << pure_node << "\" | Tipo: " << var.data_type 
              << " | Valor: " << value << std::endl;

    UA_StatusCode retval = UA_Client_writeValueAttribute(client, UA_NODEID_STRING(var.ns_index, (char*)pure_node.c_str()), &myVariant);
    UA_Variant_clear(&myVariant);
    
    if (retval == UA_STATUSCODE_GOOD) {
        std::cout << "[OPCManager] [OK] Escritura exitosa. Código: " << UA_StatusCode_name(retval) << std::endl;
        return true;
    } else {
        std::cerr << "[OPCManager] [FALLO] Error de escritura. Código: " << UA_StatusCode_name(retval) << std::endl;
        return false;
    }
}

// ============================================================
// readFloat — Lectura sincrona de un valor Float desde el PLC
// Usado para Motor_Speed en KPI (RF5)
// ============================================================
double OPCManager::readFloat(const VariableOpc& var) {
    std::lock_guard<std::mutex> lock(mtx);
    if (!is_connected) return -1.0;

    std::string pure_node = var.node_id;
    if (pure_node.substr(0, 2) == "s=") pure_node = pure_node.substr(2);

    UA_Variant value;
    UA_Variant_init(&value);

    UA_StatusCode retval = UA_Client_readValueAttribute(
        client,
        UA_NODEID_STRING(var.ns_index, (char*)pure_node.c_str()),
        &value
    );

    double result = -1.0;
    if (retval == UA_STATUSCODE_GOOD) {
        if (UA_Variant_hasScalarType(&value, &UA_TYPES[UA_TYPES_FLOAT])) {
            result = static_cast<double>(*(UA_Float*)value.data);
        } else if (UA_Variant_hasScalarType(&value, &UA_TYPES[UA_TYPES_DOUBLE])) {
            result = *(UA_Double*)value.data;
        } else if (UA_Variant_hasScalarType(&value, &UA_TYPES[UA_TYPES_INT32])) {
            result = static_cast<double>(*(UA_Int32*)value.data);
        }
    } else {
        std::cerr << "[OPCManager] [FALLO] Error leyendo '" << var.name << "' (ns=" << var.ns_index 
                  << ";s=\"" << pure_node << "\"). Código: " << UA_StatusCode_name(retval) << std::endl;
    }

    UA_Variant_clear(&value);
    return result;
}
