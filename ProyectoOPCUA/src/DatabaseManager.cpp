#include "DatabaseManager.h"
#include <iostream>
#include <sstream>
#include <iomanip>
#include <ctime>

DatabaseManager::DatabaseManager(const std::string& path) : db(nullptr), db_path(path) {}

DatabaseManager::~DatabaseManager() {
    disconnect();
}

bool DatabaseManager::connect() {
    std::lock_guard<std::mutex> lock(db_mutex);
    if (db) return true;
    if (sqlite3_open(db_path.c_str(), &db) != SQLITE_OK) {
        std::cerr << "[DB] Error abriendo DB: " << sqlite3_errmsg(db) << std::endl;
        return false;
    }
    // Habilitar WAL para concurrencia y evitar perdida de datos (RNF3)
    char* errMsg = nullptr;
    if (sqlite3_exec(db, "PRAGMA journal_mode=WAL;", nullptr, nullptr, &errMsg) != SQLITE_OK) {
        std::cerr << "[DB] Advertencia: No se pudo activar modo WAL (" 
                  << (errMsg ? errMsg : "error desconocido")
                  << "). Usando modo DELETE como fallback." << std::endl;
        if (errMsg) sqlite3_free(errMsg);
        // Fallback a modo tradicional
        sqlite3_exec(db, "PRAGMA journal_mode=DELETE;", nullptr, nullptr, nullptr);
    } else {
        sqlite3_exec(db, "PRAGMA synchronous=NORMAL;", nullptr, nullptr, nullptr);
    }
    std::cout << "[DB] Conectado a " << db_path << std::endl;
    return true;
}

void DatabaseManager::disconnect() {
    std::lock_guard<std::mutex> lock(db_mutex);
    if (db) {
        sqlite3_close(db);
        db = nullptr;
    }
}

bool DatabaseManager::executeQuery(const std::string& query) {
    char* errMsg = nullptr;
    if (sqlite3_exec(db, query.c_str(), nullptr, nullptr, &errMsg) != SQLITE_OK) {
        std::cerr << "[DB] SQL Error: " << errMsg << "\nQuery: " << query << std::endl;
        sqlite3_free(errMsg);
        return false;
    }
    return true;
}

// ============================================================
// SCHEMA: Crea tablas + inserta variables OPC del proceso
// ============================================================
bool DatabaseManager::initSchema() {
    std::lock_guard<std::mutex> lock(db_mutex);
    if (!db) return false;

    // --- Tablas de configuracion ---
    const char* schema = R"(
        CREATE TABLE IF NOT EXISTS config_opc (
            id INTEGER PRIMARY KEY,
            ip TEXT, port INTEGER, endpoint TEXT, timeout_ms INTEGER,
            auto_reconnect BOOLEAN, security_policy TEXT, auth_mode TEXT, enabled BOOLEAN
        );
        INSERT INTO config_opc (id, ip, port, endpoint, timeout_ms, auto_reconnect, security_policy, auth_mode, enabled)
        SELECT 1, '192.168.0.1', 4840, 'opc.tcp://192.168.0.1:4840', 5000, 1, 'None', 'Anonymous', 1
        WHERE NOT EXISTS (SELECT 1 FROM config_opc WHERE id = 1);

        CREATE TABLE IF NOT EXISTS config_network (
            id INTEGER PRIMARY KEY,
            iface_eth TEXT, ip_eth TEXT, mask_eth TEXT,
            iface_wifi TEXT, ssid_wifi TEXT, pass_wifi TEXT, web_port INTEGER
        );
        INSERT INTO config_network (id, iface_eth, ip_eth, mask_eth, iface_wifi, ssid_wifi, pass_wifi, web_port)
        SELECT 1, 'eth0', '192.168.0.10', '255.255.255.0', 'wlan0', 'PLC_Control', '123456789', 8080
        WHERE NOT EXISTS (SELECT 1 FROM config_network WHERE id = 1);

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

        -- RF4: Tabla de eventos de clasificacion con timestamp ISO 8601
        CREATE TABLE IF NOT EXISTS classification_events (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT    NOT NULL,
            qr_data   TEXT    NOT NULL,
            categoria INTEGER NOT NULL,
            result    TEXT    NOT NULL
        );
    )";
    if (!executeQuery(schema)) return false;

    // --- Variables OPC del proceso (RF3) ---
    // Se insertan solo si la tabla esta vacia para no duplicar
    const char* initVars = R"(
        INSERT INTO opc_variables (name, description, node_id, ns_index, data_type, unit, writable, scan_rate_ms, enabled)
        SELECT 'Motor_State', 'Estado ON/OFF del motor de la banda', 's="Bloque de datos_1"."Motor_State"', 3, 'Boolean', '', 1, 500, 1
        WHERE NOT EXISTS (SELECT 1 FROM opc_variables WHERE name = 'Motor_State');

        INSERT INTO opc_variables (name, description, node_id, ns_index, data_type, unit, writable, scan_rate_ms, enabled)
        SELECT 'Motor_Speed', 'Velocidad actual del motor (RPM)', 's="Bloque de datos_1"."Motor_Speed"', 3, 'Int32', 'RPM', 0, 500, 1
        WHERE NOT EXISTS (SELECT 1 FROM opc_variables WHERE name = 'Motor_Speed');

        INSERT INTO opc_variables (name, description, node_id, ns_index, data_type, unit, writable, scan_rate_ms, enabled)
        SELECT 'Piston1', 'Actuador neumatico Piston 1 (Categoria 1)', 's="Bloque de datos_1"."Piston1"', 3, 'Boolean', '', 1, 200, 1
        WHERE NOT EXISTS (SELECT 1 FROM opc_variables WHERE name = 'Piston1');

        INSERT INTO opc_variables (name, description, node_id, ns_index, data_type, unit, writable, scan_rate_ms, enabled)
        SELECT 'Piston2', 'Actuador neumatico Piston 2 (Categoria 2)', 's="Bloque de datos_1"."Piston2"', 3, 'Boolean', '', 1, 200, 1
        WHERE NOT EXISTS (SELECT 1 FROM opc_variables WHERE name = 'Piston2');
    )";
    return executeQuery(initVars);
}

// ============================================================
// CONFIG OPC
// ============================================================
OpcConfig DatabaseManager::getOpcConfig() {
    std::lock_guard<std::mutex> lock(db_mutex);
    OpcConfig config;
    if (!db) return config;
    sqlite3_stmt* stmt;
    const char* query = "SELECT ip, port, endpoint, timeout_ms, auto_reconnect, security_policy, auth_mode, enabled FROM config_opc WHERE id=1;";
    if (sqlite3_prepare_v2(db, query, -1, &stmt, nullptr) == SQLITE_OK) {
        if (sqlite3_step(stmt) == SQLITE_ROW) {
            config.ip              = reinterpret_cast<const char*>(sqlite3_column_text(stmt, 0));
            config.port            = sqlite3_column_int(stmt, 1);
            config.endpoint        = reinterpret_cast<const char*>(sqlite3_column_text(stmt, 2));
            config.timeout_ms      = sqlite3_column_int(stmt, 3);
            config.auto_reconnect  = sqlite3_column_int(stmt, 4);
            config.security_policy = reinterpret_cast<const char*>(sqlite3_column_text(stmt, 5));
            config.auth_mode       = reinterpret_cast<const char*>(sqlite3_column_text(stmt, 6));
            config.enabled         = sqlite3_column_int(stmt, 7);
        }
    }
    sqlite3_finalize(stmt);
    return config;
}

bool DatabaseManager::saveOpcConfig(const OpcConfig& config) {
    std::lock_guard<std::mutex> lock(db_mutex);
    if (!db) return false;
    sqlite3_stmt* stmt;
    const char* query = "UPDATE config_opc SET ip=?, port=?, endpoint=?, timeout_ms=?, auto_reconnect=?, security_policy=?, auth_mode=?, enabled=? WHERE id=1;";
    if (sqlite3_prepare_v2(db, query, -1, &stmt, nullptr) == SQLITE_OK) {
        sqlite3_bind_text(stmt, 1, config.ip.c_str(), -1, SQLITE_TRANSIENT);
        sqlite3_bind_int (stmt, 2, config.port);
        sqlite3_bind_text(stmt, 3, config.endpoint.c_str(), -1, SQLITE_TRANSIENT);
        sqlite3_bind_int (stmt, 4, config.timeout_ms);
        sqlite3_bind_int (stmt, 5, config.auto_reconnect);
        sqlite3_bind_text(stmt, 6, config.security_policy.c_str(), -1, SQLITE_TRANSIENT);
        sqlite3_bind_text(stmt, 7, config.auth_mode.c_str(), -1, SQLITE_TRANSIENT);
        sqlite3_bind_int (stmt, 8, config.enabled);
        sqlite3_step(stmt);
    }
    sqlite3_finalize(stmt);
    return true;
}

// ============================================================
// CONFIG NETWORK
// ============================================================
NetworkConfig DatabaseManager::getNetworkConfig() {
    std::lock_guard<std::mutex> lock(db_mutex);
    NetworkConfig config;
    if (!db) return config;
    sqlite3_stmt* stmt;
    const char* query = "SELECT iface_eth, ip_eth, mask_eth, iface_wifi, ssid_wifi, pass_wifi, web_port FROM config_network WHERE id=1;";
    if (sqlite3_prepare_v2(db, query, -1, &stmt, nullptr) == SQLITE_OK) {
        if (sqlite3_step(stmt) == SQLITE_ROW) {
            config.iface_eth  = reinterpret_cast<const char*>(sqlite3_column_text(stmt, 0));
            config.ip_eth     = reinterpret_cast<const char*>(sqlite3_column_text(stmt, 1));
            config.mask_eth   = reinterpret_cast<const char*>(sqlite3_column_text(stmt, 2));
            config.iface_wifi = reinterpret_cast<const char*>(sqlite3_column_text(stmt, 3));
            config.ssid_wifi  = reinterpret_cast<const char*>(sqlite3_column_text(stmt, 4));
            config.pass_wifi  = reinterpret_cast<const char*>(sqlite3_column_text(stmt, 5));
            config.web_port   = sqlite3_column_int(stmt, 6);
        }
    }
    sqlite3_finalize(stmt);
    return config;
}

bool DatabaseManager::saveNetworkConfig(const NetworkConfig& config) {
    std::lock_guard<std::mutex> lock(db_mutex);
    if (!db) return false;
    sqlite3_stmt* stmt;
    const char* query = "UPDATE config_network SET iface_eth=?, ip_eth=?, mask_eth=?, iface_wifi=?, ssid_wifi=?, pass_wifi=?, web_port=? WHERE id=1;";
    if (sqlite3_prepare_v2(db, query, -1, &stmt, nullptr) == SQLITE_OK) {
        sqlite3_bind_text(stmt, 1, config.iface_eth.c_str(),  -1, SQLITE_TRANSIENT);
        sqlite3_bind_text(stmt, 2, config.ip_eth.c_str(),     -1, SQLITE_TRANSIENT);
        sqlite3_bind_text(stmt, 3, config.mask_eth.c_str(),   -1, SQLITE_TRANSIENT);
        sqlite3_bind_text(stmt, 4, config.iface_wifi.c_str(), -1, SQLITE_TRANSIENT);
        sqlite3_bind_text(stmt, 5, config.ssid_wifi.c_str(),  -1, SQLITE_TRANSIENT);
        sqlite3_bind_text(stmt, 6, config.pass_wifi.c_str(),  -1, SQLITE_TRANSIENT);
        sqlite3_bind_int (stmt, 7, config.web_port);
        sqlite3_step(stmt);
    }
    sqlite3_finalize(stmt);
    return true;
}

// ============================================================
// VARIABLES OPC
// ============================================================
static VariableOpc rowToVar(sqlite3_stmt* stmt) {
    VariableOpc v;
    auto safeText = [&](int col) -> std::string {
        const unsigned char* t = sqlite3_column_text(stmt, col);
        return t ? reinterpret_cast<const char*>(t) : "";
    };
    v.id           = sqlite3_column_int(stmt, 0);
    v.name         = safeText(1);
    v.description  = safeText(2);
    v.node_id      = safeText(3);
    v.ns_index     = sqlite3_column_int(stmt, 4);
    v.data_type    = safeText(5);
    v.unit         = safeText(6);
    v.writable     = sqlite3_column_int(stmt, 7);
    v.scan_rate_ms = sqlite3_column_int(stmt, 8);
    v.enabled      = sqlite3_column_int(stmt, 9);
    return v;
}

std::vector<VariableOpc> DatabaseManager::getAllVariables() {
    std::lock_guard<std::mutex> lock(db_mutex);
    std::vector<VariableOpc> vars;
    if (!db) return vars;
    sqlite3_stmt* stmt;
    const char* query = "SELECT id, name, description, node_id, ns_index, data_type, unit, writable, scan_rate_ms, enabled FROM opc_variables ORDER BY id;";
    if (sqlite3_prepare_v2(db, query, -1, &stmt, nullptr) == SQLITE_OK) {
        while (sqlite3_step(stmt) == SQLITE_ROW)
            vars.push_back(rowToVar(stmt));
    }
    sqlite3_finalize(stmt);
    return vars;
}

std::vector<VariableOpc> DatabaseManager::getEnabledVariables() {
    auto vars = getAllVariables();
    std::vector<VariableOpc> enabled;
    for (const auto& v : vars)
        if (v.enabled) enabled.push_back(v);
    return enabled;
}

bool DatabaseManager::saveVariable(const VariableOpc& var) {
    std::lock_guard<std::mutex> lock(db_mutex);
    if (!db) return false;
    sqlite3_stmt* stmt;
    const char* query = "INSERT INTO opc_variables (name, description, node_id, ns_index, data_type, unit, writable, scan_rate_ms, enabled) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);";
    if (sqlite3_prepare_v2(db, query, -1, &stmt, nullptr) == SQLITE_OK) {
        sqlite3_bind_text(stmt, 1, var.name.c_str(),        -1, SQLITE_TRANSIENT);
        sqlite3_bind_text(stmt, 2, var.description.c_str(), -1, SQLITE_TRANSIENT);
        sqlite3_bind_text(stmt, 3, var.node_id.c_str(),     -1, SQLITE_TRANSIENT);
        sqlite3_bind_int (stmt, 4, var.ns_index);
        sqlite3_bind_text(stmt, 5, var.data_type.c_str(),   -1, SQLITE_TRANSIENT);
        sqlite3_bind_text(stmt, 6, var.unit.c_str(),        -1, SQLITE_TRANSIENT);
        sqlite3_bind_int (stmt, 7, var.writable);
        sqlite3_bind_int (stmt, 8, var.scan_rate_ms);
        sqlite3_bind_int (stmt, 9, var.enabled);
        sqlite3_step(stmt);
    }
    sqlite3_finalize(stmt);
    return true;
}

bool DatabaseManager::updateVariable(const VariableOpc& var) {
    std::lock_guard<std::mutex> lock(db_mutex);
    if (!db) return false;
    sqlite3_stmt* stmt;
    const char* query = "UPDATE opc_variables SET name=?, description=?, node_id=?, ns_index=?, data_type=?, unit=?, writable=?, scan_rate_ms=?, enabled=? WHERE id=?;";
    if (sqlite3_prepare_v2(db, query, -1, &stmt, nullptr) == SQLITE_OK) {
        sqlite3_bind_text(stmt, 1, var.name.c_str(),        -1, SQLITE_TRANSIENT);
        sqlite3_bind_text(stmt, 2, var.description.c_str(), -1, SQLITE_TRANSIENT);
        sqlite3_bind_text(stmt, 3, var.node_id.c_str(),     -1, SQLITE_TRANSIENT);
        sqlite3_bind_int (stmt, 4, var.ns_index);
        sqlite3_bind_text(stmt, 5, var.data_type.c_str(),   -1, SQLITE_TRANSIENT);
        sqlite3_bind_text(stmt, 6, var.unit.c_str(),        -1, SQLITE_TRANSIENT);
        sqlite3_bind_int (stmt, 7, var.writable);
        sqlite3_bind_int (stmt, 8, var.scan_rate_ms);
        sqlite3_bind_int (stmt, 9, var.enabled);
        sqlite3_bind_int (stmt, 10, var.id);
        sqlite3_step(stmt);
    }
    sqlite3_finalize(stmt);
    return true;
}

bool DatabaseManager::deleteVariable(int id) {
    std::lock_guard<std::mutex> lock(db_mutex);
    if (!db) return false;
    sqlite3_stmt* stmt;
    const char* query = "DELETE FROM opc_variables WHERE id=?;";
    if (sqlite3_prepare_v2(db, query, -1, &stmt, nullptr) == SQLITE_OK) {
        sqlite3_bind_int(stmt, 1, id);
        sqlite3_step(stmt);
    }
    sqlite3_finalize(stmt);
    return true;
}

std::optional<VariableOpc> DatabaseManager::getVariable(int id) {
    std::lock_guard<std::mutex> lock(db_mutex);
    if (!db) return std::nullopt;
    sqlite3_stmt* stmt;
    const char* query = "SELECT id, name, description, node_id, ns_index, data_type, unit, writable, scan_rate_ms, enabled FROM opc_variables WHERE id=?;";
    if (sqlite3_prepare_v2(db, query, -1, &stmt, nullptr) == SQLITE_OK) {
        sqlite3_bind_int(stmt, 1, id);
        if (sqlite3_step(stmt) == SQLITE_ROW) {
            VariableOpc v = rowToVar(stmt);
            sqlite3_finalize(stmt);
            return v;
        }
    }
    sqlite3_finalize(stmt);
    return std::nullopt;
}

// ============================================================
// LOGS GENERICOS
// ============================================================
bool DatabaseManager::logData(int variable_id, const std::string& value) {
    std::lock_guard<std::mutex> lock(db_mutex);
    if (!db) return false;
    sqlite3_stmt* stmt;
    const char* query = "INSERT INTO data_logs (variable_id, value_str) VALUES (?, ?);";
    if (sqlite3_prepare_v2(db, query, -1, &stmt, nullptr) == SQLITE_OK) {
        sqlite3_bind_int (stmt, 1, variable_id);
        sqlite3_bind_text(stmt, 2, value.c_str(), -1, SQLITE_TRANSIENT);
        sqlite3_step(stmt);
    }
    sqlite3_finalize(stmt);
    return true;
}

bool DatabaseManager::logSystem(const std::string& level, const std::string& message) {
    std::lock_guard<std::mutex> lock(db_mutex);
    if (!db) return false;
    sqlite3_stmt* stmt;
    const char* query = "INSERT INTO system_logs (level, message) VALUES (?, ?);";
    if (sqlite3_prepare_v2(db, query, -1, &stmt, nullptr) == SQLITE_OK) {
        sqlite3_bind_text(stmt, 1, level.c_str(),   -1, SQLITE_TRANSIENT);
        sqlite3_bind_text(stmt, 2, message.c_str(), -1, SQLITE_TRANSIENT);
        sqlite3_step(stmt);
    }
    sqlite3_finalize(stmt);
    return true;
}

std::vector<SystemLog> DatabaseManager::getRecentSystemLogs(int limit) {
    std::lock_guard<std::mutex> lock(db_mutex);
    std::vector<SystemLog> logs;
    if (!db) return logs;

    sqlite3_stmt* stmt;
    std::string query =
        "SELECT id, timestamp, level, message "
        "FROM system_logs ORDER BY id DESC LIMIT " + std::to_string(limit) + ";";

    if (sqlite3_prepare_v2(db, query.c_str(), -1, &stmt, nullptr) == SQLITE_OK) {
        while (sqlite3_step(stmt) == SQLITE_ROW) {
            SystemLog l;
            auto safeText = [&](int col) -> std::string {
                const unsigned char* t = sqlite3_column_text(stmt, col);
                return t ? reinterpret_cast<const char*>(t) : "";
            };
            l.id        = sqlite3_column_int(stmt, 0);
            l.timestamp = safeText(1);
            l.level     = safeText(2);
            l.message   = safeText(3);
            logs.push_back(l);
        }
    }
    sqlite3_finalize(stmt);
    return logs;
}

// ============================================================
// RF4: EVENTOS DE CLASIFICACION
// ============================================================
bool DatabaseManager::logClassificationEvent(const ClassificationEvent& event) {
    std::lock_guard<std::mutex> lock(db_mutex);
    if (!db) return false;

    sqlite3_stmt* stmt;
    const char* query =
        "INSERT INTO classification_events (timestamp, qr_data, categoria, result) "
        "VALUES (?, ?, ?, ?);";
    bool ok = false;
    if (sqlite3_prepare_v2(db, query, -1, &stmt, nullptr) == SQLITE_OK) {
        sqlite3_bind_text(stmt, 1, event.timestamp.c_str(), -1, SQLITE_TRANSIENT);
        sqlite3_bind_text(stmt, 2, event.qr_data.c_str(),   -1, SQLITE_TRANSIENT);
        sqlite3_bind_int (stmt, 3, event.categoria);
        sqlite3_bind_text(stmt, 4, event.result.c_str(),    -1, SQLITE_TRANSIENT);
        ok = (sqlite3_step(stmt) == SQLITE_DONE);
    }
    sqlite3_finalize(stmt);

    if (ok) {
        std::cout << "[DB] Evento registrado: QR=" << event.qr_data
                  << " Cat=" << event.categoria
                  << " Result=" << event.result
                  << " @ " << event.timestamp << std::endl;
    }
    return ok;
}

std::vector<ClassificationEvent> DatabaseManager::getRecentEvents(int limit) {
    std::lock_guard<std::mutex> lock(db_mutex);
    std::vector<ClassificationEvent> events;
    if (!db) return events;

    sqlite3_stmt* stmt;
    std::string query =
        "SELECT id, timestamp, qr_data, categoria, result "
        "FROM classification_events ORDER BY id DESC LIMIT " + std::to_string(limit) + ";";

    if (sqlite3_prepare_v2(db, query.c_str(), -1, &stmt, nullptr) == SQLITE_OK) {
        while (sqlite3_step(stmt) == SQLITE_ROW) {
            ClassificationEvent e;
            auto safeText = [&](int col) -> std::string {
                const unsigned char* t = sqlite3_column_text(stmt, col);
                return t ? reinterpret_cast<const char*>(t) : "";
            };
            e.id        = sqlite3_column_int(stmt, 0);
            e.timestamp = safeText(1);
            e.qr_data   = safeText(2);
            e.categoria = sqlite3_column_int(stmt, 3);
            e.result    = safeText(4);
            events.push_back(e);
        }
    }
    sqlite3_finalize(stmt);
    return events;
}

// ============================================================
// RF5: ESTADO DEL SISTEMA (conteos KPI desde DB)
// ============================================================
SystemState DatabaseManager::getSystemState() {
    std::lock_guard<std::mutex> lock(db_mutex);
    SystemState state;
    if (!db) return state;

    // Conteo por categoria (RF5.3)
    sqlite3_stmt* stmt;
    const char* query =
        "SELECT categoria, COUNT(*) FROM classification_events GROUP BY categoria;";
    if (sqlite3_prepare_v2(db, query, -1, &stmt, nullptr) == SQLITE_OK) {
        while (sqlite3_step(stmt) == SQLITE_ROW) {
            int cat   = sqlite3_column_int(stmt, 0);
            int count = sqlite3_column_int(stmt, 1);
            switch (cat) {
                case 1: state.count_cat1 = count; break;
                case 2: state.count_cat2 = count; break;
                case 3: state.count_cat3 = count; break;
                default: state.count_otro += count; break;
            }
            state.total_classified += count;
        }
    }
    sqlite3_finalize(stmt);

    // Ultimo evento
    const char* lastQ =
        "SELECT timestamp, qr_data, categoria FROM classification_events ORDER BY id DESC LIMIT 1;";
    if (sqlite3_prepare_v2(db, lastQ, -1, &stmt, nullptr) == SQLITE_OK) {
        if (sqlite3_step(stmt) == SQLITE_ROW) {
            auto safeText = [&](int col) -> std::string {
                const unsigned char* t = sqlite3_column_text(stmt, col);
                return t ? reinterpret_cast<const char*>(t) : "";
            };
            state.last_event_time = safeText(0);
            state.last_qr_data    = safeText(1);
            state.last_categoria  = sqlite3_column_int(stmt, 2);
        }
    }
    sqlite3_finalize(stmt);

    return state;
}
