#include "ConfigManager.h"

ConfigManager::ConfigManager(DatabaseManager* db) : db(db) {}

void ConfigManager::load() {
    opc_config = db->getOpcConfig();
    net_config = db->getNetworkConfig();
}

OpcConfig ConfigManager::getOpcConfig() const {
    return opc_config;
}

void ConfigManager::setOpcConfig(const OpcConfig& cfg) {
    opc_config = cfg;
    db->saveOpcConfig(cfg);
}

NetworkConfig ConfigManager::getNetworkConfig() const {
    return net_config;
}

void ConfigManager::setNetworkConfig(const NetworkConfig& cfg) {
    net_config = cfg;
    db->saveNetworkConfig(cfg);
}
