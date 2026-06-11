#pragma once
#include "DatabaseManager.h"
#include "models/ConfigModels.h"

class ConfigManager {
private:
    DatabaseManager* db;
    OpcConfig opc_config;
    NetworkConfig net_config;

public:
    ConfigManager(DatabaseManager* db);
    void load();
    
    OpcConfig getOpcConfig() const;
    void setOpcConfig(const OpcConfig& cfg);

    NetworkConfig getNetworkConfig() const;
    void setNetworkConfig(const NetworkConfig& cfg);

    // Acceso directo a la DB para modulos que lo requieren
    DatabaseManager* getDb() const { return db; }
};
