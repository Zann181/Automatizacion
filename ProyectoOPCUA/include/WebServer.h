#pragma once

// SSL es requerido para que getUserMedia() funcione en navegadores moviles.
// Definir CPPHTTPLIB_OPENSSL_SUPPORT antes de incluir httplib.h
#ifdef CPPHTTPLIB_OPENSSL_SUPPORT
  // Ya definido por el compilador via -DCPPHTTPLIB_OPENSSL_SUPPORT
#endif
#include "httplib.h"

#include "ConfigManager.h"
#include "VariableManager.h"
#include "OPCManager.h"
#include "NetworkManager.h"
#include "ClassificationManager.h"
#include <thread>
#include <atomic>
#include <string>

class WebServer {
private:
    // Elegir SSLServer o Server segun soporte SSL compilado
#ifdef CPPHTTPLIB_OPENSSL_SUPPORT
    httplib::SSLServer svr;
#else
    httplib::Server svr;
#endif

    ConfigManager*         configMgr;
    VariableManager*       varMgr;
    OPCManager*            opcMgr;
    NetworkManager*        netMgr;
    ClassificationManager* classMgr;

    std::thread       server_thread;
    std::atomic<bool> running;

    // Helpers de serializacion JSON (sin dependencias externas)
    std::string varToJson(const VariableOpc& v);
    std::string eventToJson(const ClassificationEvent& e);
    std::string stateToJson(const SystemState& s);
    std::string escapeJson(const std::string& s);

public:
    // cert_path y key_path solo se usan cuando USE_SSL=1
    WebServer(ConfigManager* cm, VariableManager* vm,
              OPCManager* om, NetworkManager* nm,
              ClassificationManager* clsMgr,
              const std::string& cert_path = "certs/cert.pem",
              const std::string& key_path  = "certs/key.pem");
    ~WebServer();

    void setupRoutes();
    void start(int port);
    void stop();
};
