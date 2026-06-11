#pragma once
#include <sqlite3.h>
#include <string>
#include <mutex>
#include <vector>
#include <optional>
#include "models/VariableOpc.h"
#include "models/ConfigModels.h"

class DatabaseManager {
private:
    sqlite3*    db;
    std::mutex  db_mutex;
    std::string db_path;

    bool executeQuery(const std::string& query);

public:
    DatabaseManager(const std::string& path = "config_plc.db");
    ~DatabaseManager();

    bool connect();
    void disconnect();
    bool initSchema();          // Crea tablas + datos iniciales OPC del proceso

    // ---- Variables OPC (configuracion dinamica) ----
    std::vector<VariableOpc> getAllVariables();
    std::vector<VariableOpc> getEnabledVariables();
    bool saveVariable(const VariableOpc& var);
    bool updateVariable(const VariableOpc& var);
    bool deleteVariable(int id);
    std::optional<VariableOpc> getVariable(int id);

    // ---- Configuracion OPC ----
    OpcConfig getOpcConfig();
    bool      saveOpcConfig(const OpcConfig& config);

    // ---- Configuracion de red ----
    NetworkConfig getNetworkConfig();
    bool          saveNetworkConfig(const NetworkConfig& config);

    // ---- Logs genericos del sistema ----
    bool logData(int variable_id, const std::string& value);
    bool logSystem(const std::string& level, const std::string& message);
    std::vector<SystemLog> getRecentSystemLogs(int limit = 50);

    // ---- RF4: Eventos de clasificacion ----
    bool logClassificationEvent(const ClassificationEvent& event);
    std::vector<ClassificationEvent> getRecentEvents(int limit = 50);

    // ---- RF5: Estado del sistema (conteos KPI) ----
    SystemState getSystemState();
};
