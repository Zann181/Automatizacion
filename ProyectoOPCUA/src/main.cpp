#include <iostream>
#include <string>
#include <vector>
#ifndef _WIN32
#include <ifaddrs.h>
#include <netinet/in.h>
#include <arpa/inet.h>
#endif

#include "DatabaseManager.h"
#include "ConfigManager.h"
#include "NetworkManager.h"
#include "OPCManager.h"
#include "VariableManager.h"
#include "ClassificationManager.h"
#include "WebServer.h"

void printAccessInstructions(int port) {
    std::vector<std::pair<std::string, std::string>> ips;
#ifndef _WIN32
    struct ifaddrs* ifaddr;
    if (getifaddrs(&ifaddr) != -1) {
        for (struct ifaddrs* ifa = ifaddr; ifa != nullptr; ifa = ifa->ifa_next) {
            if (ifa->ifa_addr == nullptr) continue;
            if (ifa->ifa_addr->sa_family == AF_INET) { // IPv4
                std::string ifaceName = ifa->ifa_name;
                if (ifaceName != "lo") { // Exclude loopback
                    char ip[INET_ADDRSTRLEN];
                    void* addr = &((struct sockaddr_in*)ifa->ifa_addr)->sin_addr;
                    inet_ntop(AF_INET, addr, ip, INET_ADDRSTRLEN);
                    ips.push_back({ifaceName, std::string(ip)});
                }
            }
        }
        freeifaddrs(ifaddr);
    }
#endif

    std::cout << "\n==================================================" << std::endl;
    std::cout << "  [MAIN] ¡Sistema en ejecucion de forma segura!" << std::endl;
    std::cout << "==================================================" << std::endl;
#ifdef CPPHTTPLIB_OPENSSL_SUPPORT
    std::cout << " Puedes acceder al Dashboard HTTPS desde tu navegador:" << std::endl;
    for (const auto& pair : ips) {
        std::cout << "   -> [" << pair.first << "]: https://" << pair.second << ":" << port << std::endl;
    }
    if (ips.empty()) {
        std::cout << "   -> https://127.0.0.1:" << port << std::endl;
    }
    std::cout << "\n [NOTA] Acepta el certificado autofirmado la primera vez" << std::endl;
    std::cout << "        en tu navegador (Avanzado -> Continuar)." << std::endl;
#else
    std::cout << " Puedes acceder al Dashboard HTTP desde tu navegador:" << std::endl;
    for (const auto& pair : ips) {
        std::cout << "   -> [" << pair.first << "]: http://" << pair.second << ":" << port << std::endl;
    }
    if (ips.empty()) {
        std::cout << "   -> http://127.0.0.1:" << port << std::endl;
    }
    std::cout << "\n [AVISO] La camara en moviles requiere SSL (HTTPS)." << std::endl;
    std::cout << "         Recompila ejecutando: make USE_SSL=1" << std::endl;
#endif
    std::cout << "==================================================" << std::endl;
    std::cout << " Comandos de consola: 'qr N' (prueba), 'status', 'salir'\n" << std::endl;
}

int main() {
    std::cout << "==================================================" << std::endl;
    std::cout << "  Sistema de Clasificacion por Vision Artificial   " << std::endl;
    std::cout << "  Raspberry Pi - OPC UA Client + HTTPS WebServer   " << std::endl;
    std::cout << "==================================================" << std::endl;

    // 1. Base de datos (SQLite WAL para RNF3: 0% perdida)
    DatabaseManager db("config_plc.db");
    if (!db.connect() || !db.initSchema()) {
        std::cerr << "[MAIN] Fallo critico: No se pudo inicializar la base de datos." << std::endl;
        return 1;
    }

    // 2. Configuracion (OPC + Red)
    ConfigManager configMgr(&db);
    configMgr.load();

    // 3. Red
    NetworkManager netMgr;

    // 4. OPC-UA Manager + Variables
    OPCManager opcMgr;
    VariableManager varMgr(&db, &opcMgr);

    auto opcCfg = configMgr.getOpcConfig();
    if (opcCfg.enabled) {
        std::cout << "[MAIN] Conectando a PLC: " << opcCfg.endpoint << std::endl;
        if (opcMgr.connect(opcCfg.endpoint, opcCfg.timeout_ms)) {
            varMgr.loadAndSubscribeAll();
            std::cout << "[MAIN] OPC-UA conectado." << std::endl;
            db.logSystem("INFO", "Conexion exitosa con el PLC en " + opcCfg.endpoint);
        } else {
            std::cerr << "[MAIN] PLC no alcanzable. Modo local activado." << std::endl;
            db.logSystem("WARN", "PLC no alcanzable en " + opcCfg.endpoint + ". Iniciando en Modo Local.");
        }
    }

    // 5. Clasificacion (FSM: RF2, RF3, RF4)
    ClassificationManager classMgr(&db, &opcMgr);

    // Hilo de polling de Motor_Speed desde el PLC (RF5 — KPI velocidad real)
    // Corre a la misma cadencia del frontend (800ms) para mantener sincronía
    std::atomic<bool> kpi_running(true);
    std::thread kpi_thread([&]() {
        while (kpi_running) {
            classMgr.refreshOpcState();   // Lee Motor_Speed via OPC-UA
            std::this_thread::sleep_for(std::chrono::milliseconds(800));
        }
    });

    // 6. Servidor Web HTTPS (puerto 8443 para HTTPS, requerido para camara movil)
    //    Certificados generados con: ./scripts/generar_certificados.sh
    const std::string CERT = "certs/cert.pem";
    const std::string KEY  = "certs/key.pem";
    const int WEB_PORT = 8443;  // HTTPS

    WebServer webServer(&configMgr, &varMgr, &opcMgr, &netMgr, &classMgr, CERT, KEY);
    webServer.setupRoutes();
    webServer.start(WEB_PORT);

    printAccessInstructions(WEB_PORT);

    // Bucle interactivo
    std::string comando;
    while (true) {
        std::getline(std::cin, comando);
        if (comando == "salir" || comando == "exit" || comando == "q") break;

        if (comando.rfind("qr ", 0) == 0) {
            std::string qr_val = comando.substr(3);
            std::cout << "[MAIN] Procesando QR manual: " << qr_val << std::endl;
            classMgr.processQR(qr_val);
        }
        if (comando == "status") {
            auto st = classMgr.getSystemState();
            std::cout << "[STATUS]"
                      << " Motor=" << (st.motor_running ? "ON" : "OFF")
                      << " | P1=" << (st.piston1_active ? "ACT" : "off")
                      << " | P2=" << (st.piston2_active ? "ACT" : "off")
                      << " | Cat1=" << st.count_cat1
                      << " Cat2=" << st.count_cat2
                      << " Cat3=" << st.count_cat3
                      << " Otro=" << st.count_otro
                      << " | FSM=" << st.fsm_state << std::endl;
        }
    }

    // Apagado ordenado
    kpi_running = false;
    if (kpi_thread.joinable()) kpi_thread.join();
    webServer.stop();
    opcMgr.disconnect();
    db.disconnect();

    std::cout << "[MAIN] Sistema apagado." << std::endl;
    return 0;
}
