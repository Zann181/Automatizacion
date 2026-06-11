#pragma once
#include "models/ConfigModels.h"

class NetworkManager {
public:
    NetworkManager();
    bool applyEthernetConfig(const NetworkConfig& config);
    bool applyWifiConfig(const NetworkConfig& config);
};
