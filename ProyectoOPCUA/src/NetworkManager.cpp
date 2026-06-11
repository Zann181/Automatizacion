#include "NetworkManager.h"
#include <cstdlib>
#include <iostream>
#include <string>

NetworkManager::NetworkManager() {}

bool NetworkManager::applyEthernetConfig(const NetworkConfig& config) {
    // Aquí se llamaría a un script bash que configure nmcli o dhcpcd con los parámetros.
    // Por seguridad e independecia de sudo, lo enviamos como comando nohup.
    std::string cmd = "nohup sudo bash scripts/configurar_ethernet.sh " + config.iface_eth + " " + config.ip_eth + " " + config.mask_eth + " > /dev/null 2>&1 &";
    std::cout << "Aplicando red Ethernet: " << cmd << std::endl;
    int ret = std::system(cmd.c_str());
    return (ret == 0);
}

bool NetworkManager::applyWifiConfig(const NetworkConfig& config) {
    std::string cmd = "nohup sudo bash scripts/setup_wifi.sh " + config.iface_wifi + " " + config.ssid_wifi + " " + config.pass_wifi + " > /dev/null 2>&1 &";
    std::cout << "Aplicando red WiFi: " << cmd << std::endl;
    int ret = std::system(cmd.c_str());
    return (ret == 0);
}
