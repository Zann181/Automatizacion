#include "WebServer.h"
#include <iostream>
#include <sstream>

// ============================================================
// Constructor — elige SSLServer o Server segun flag de compilacion
// ============================================================
#ifdef CPPHTTPLIB_OPENSSL_SUPPORT
WebServer::WebServer(ConfigManager* cm, VariableManager* vm,
                     OPCManager* om, NetworkManager* nm,
                     ClassificationManager* clsMgr,
                     const std::string& cert_path,
                     const std::string& key_path)
    : svr(cert_path.c_str(), key_path.c_str()),   // SSLServer necesita cert+key
      configMgr(cm), varMgr(vm), opcMgr(om), netMgr(nm),
      classMgr(clsMgr), running(false)
{
    std::cout << "[WebServer] Modo HTTPS habilitado." << std::endl;
    std::cout << "[WebServer] Cert: " << cert_path << "  Key: " << key_path << std::endl;
    if (!svr.is_valid()) {
        std::cerr << "[WebServer] ERROR: Certificados no encontrados o invalidos." << std::endl;
        std::cerr << "  Genera los certificados con: ./scripts/generar_certificados.sh" << std::endl;
    }
}
#else
WebServer::WebServer(ConfigManager* cm, VariableManager* vm,
                     OPCManager* om, NetworkManager* nm,
                     ClassificationManager* clsMgr,
                     const std::string& /*cert_path*/,
                     const std::string& /*key_path*/)
    : configMgr(cm), varMgr(vm), opcMgr(om), netMgr(nm),
      classMgr(clsMgr), running(false)
{
    std::cout << "[WebServer] Modo HTTP (sin SSL). "
              << "La camara NO funcionara en dispositivos moviles." << std::endl;
    std::cout << "[WebServer] Recompila con: make USE_SSL=1" << std::endl;
}
#endif

WebServer::~WebServer() {
    stop();
}

// ============================================================
// Helpers JSON
// ============================================================
std::string WebServer::escapeJson(const std::string& s) {
    std::string out;
    for (char c : s) {
        switch (c) {
            case '"':  out += "\\\""; break;
            case '\\': out += "\\\\"; break;
            case '\n': out += "\\n";  break;
            case '\r': out += "\\r";  break;
            case '\t': out += "\\t";  break;
            default:   out += c;      break;
        }
    }
    return out;
}

std::string WebServer::varToJson(const VariableOpc& v) {
    return "{\"id\":" + std::to_string(v.id) +
           ",\"name\":\"" + escapeJson(v.name) + "\"" +
           ",\"description\":\"" + escapeJson(v.description) + "\"" +
           ",\"node_id\":\"" + escapeJson(v.node_id) + "\"" +
           ",\"ns_index\":" + std::to_string(v.ns_index) +
           ",\"data_type\":\"" + escapeJson(v.data_type) + "\"" +
           ",\"unit\":\"" + escapeJson(v.unit) + "\"" +
           ",\"writable\":" + (v.writable ? "true" : "false") +
           ",\"scan_rate_ms\":" + std::to_string(v.scan_rate_ms) +
           ",\"enabled\":" + (v.enabled ? "true" : "false") + "}";
}

std::string WebServer::eventToJson(const ClassificationEvent& e) {
    return "{\"id\":" + std::to_string(e.id) +
           ",\"timestamp\":\"" + escapeJson(e.timestamp) + "\"" +
           ",\"qr_data\":\"" + escapeJson(e.qr_data) + "\"" +
           ",\"categoria\":" + std::to_string(e.categoria) +
           ",\"result\":\"" + escapeJson(e.result) + "\"}";
}

std::string WebServer::stateToJson(const SystemState& s) {
    return "{\"motor_speed\":" + std::to_string(s.motor_speed) +
           ",\"motor_running\":" + (s.motor_running ? "true" : "false") +
           ",\"piston1_active\":" + (s.piston1_active ? "true" : "false") +
           ",\"piston2_active\":" + (s.piston2_active ? "true" : "false") +
           ",\"count_cat1\":" + std::to_string(s.count_cat1) +
           ",\"count_cat2\":" + std::to_string(s.count_cat2) +
           ",\"count_cat3\":" + std::to_string(s.count_cat3) +
           ",\"count_otro\":" + std::to_string(s.count_otro) +
           ",\"total_classified\":" + std::to_string(s.total_classified) +
           ",\"last_event_time\":\"" + escapeJson(s.last_event_time) + "\"" +
           ",\"last_qr_data\":\"" + escapeJson(s.last_qr_data) + "\"" +
           ",\"last_categoria\":" + std::to_string(s.last_categoria) +
           ",\"fsm_state\":\"" + escapeJson(s.fsm_state) + "\"}";
}

// ============================================================
// Rutas REST
// ============================================================
void WebServer::setupRoutes() {
    // Archivos estaticos desde ./web
    svr.set_base_dir("./web");

    // Cabeceras CORS
    svr.set_default_headers({
        {"Access-Control-Allow-Origin",  "*"},
        {"Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS"},
        {"Access-Control-Allow-Headers", "Content-Type"},
        // Requerido para que el navegador permita getUserMedia sobre HTTPS propio
        {"Cross-Origin-Opener-Policy",   "same-origin"},
        {"Cross-Origin-Embedder-Policy", "require-corp"}
    });

    svr.Options(".*", [](const httplib::Request&, httplib::Response& res) {
        res.status = 204;
    });

    // ===== API OPC-UA Config =====
    svr.Get("/api/opc", [this](const httplib::Request&, httplib::Response& res) {
        auto cfg = configMgr->getOpcConfig();
        std::string json =
            "{\"ip\":\"" + cfg.ip + "\""
            ",\"port\":" + std::to_string(cfg.port) +
            ",\"endpoint\":\"" + cfg.endpoint + "\""
            ",\"timeout_ms\":" + std::to_string(cfg.timeout_ms) +
            ",\"enabled\":" + (cfg.enabled ? "true" : "false") +
            ",\"connected\":" + (opcMgr->isConnected() ? "true" : "false") + "}";
        res.set_content(json, "application/json");
    });

    // Guardar nueva configuracion OPC (PUT /api/opc)
    svr.Put("/api/opc", [this](const httplib::Request& req, httplib::Response& res) {
        auto extractStr = [&](const std::string& key) -> std::string {
            std::string search = "\"" + key + "\":\"";
            auto pos = req.body.find(search);
            if (pos == std::string::npos) return "";
            pos += search.size();
            auto end = req.body.find("\"", pos);
            return req.body.substr(pos, end - pos);
        };
        auto extractInt = [&](const std::string& key, int def) -> int {
            std::string search = "\"" + key + "\":";
            auto pos = req.body.find(search);
            if (pos == std::string::npos) return def;
            pos += search.size();
            while (pos < req.body.size() && req.body[pos] == ' ') pos++;
            auto end = req.body.find_first_of(",}", pos);
            try { return std::stoi(req.body.substr(pos, end - pos)); } catch (...) { return def; }
        };

        OpcConfig cfg = configMgr->getOpcConfig(); // partir de la config actual
        std::string newIp   = extractStr("ip");
        std::string newEp   = extractStr("endpoint");
        int         newPort = extractInt("port", 0);

        if (!newIp.empty())   cfg.ip       = newIp;
        if (!newEp.empty())   cfg.endpoint = newEp;
        if (newPort > 0)      cfg.port     = newPort;

        // Si no vino endpoint pero si IP+puerto, reconstruirlo
        if (newEp.empty() && !newIp.empty() && newPort > 0)
            cfg.endpoint = "opc.tcp://" + cfg.ip + ":" + std::to_string(cfg.port);

        configMgr->setOpcConfig(cfg);
        std::cout << "[WebServer] Config OPC guardada: " << cfg.ip << ":" << cfg.port << std::endl;
        res.set_content("{\"status\":\"saved\"}", "application/json");
    });

    svr.Post("/api/opc/reconnect", [this](const httplib::Request&, httplib::Response& res) {
        auto cfg = configMgr->getOpcConfig();
        opcMgr->disconnect();
        if (cfg.enabled) {
            opcMgr->connect(cfg.endpoint, cfg.timeout_ms);
            varMgr->loadAndSubscribeAll();
        }
        res.set_content("{\"status\":\"reconnected\"}", "application/json");
    });

    // ===== Variables OPC (lista real desde DB) =====
    svr.Get("/api/variables", [this](const httplib::Request&, httplib::Response& res) {
        auto vars = varMgr->getAllVariables();
        std::string json = "[";
        for (size_t i = 0; i < vars.size(); i++) {
            json += varToJson(vars[i]);
            if (i + 1 < vars.size()) json += ",";
        }
        json += "]";
        res.set_content(json, "application/json");
    });

    svr.Post("/api/variables", [this](const httplib::Request& req, httplib::Response& res) {
        auto extract = [&](const std::string& key) -> std::string {
            std::string search = "\"" + key + "\":\"";
            auto pos = req.body.find(search);
            if (pos == std::string::npos) return "";
            pos += search.size();
            auto end = req.body.find("\"", pos);
            return req.body.substr(pos, end - pos);
        };
        VariableOpc var;
        var.name        = extract("name");
        var.node_id     = extract("node_id");
        var.description = extract("description");
        var.data_type   = extract("data_type");
        if (var.data_type.empty()) var.data_type = "Float";
        var.ns_index     = 2;
        var.writable     = false;
        var.scan_rate_ms = 1000;
        var.enabled      = true;

        if (var.name.empty() || var.node_id.empty()) {
            res.status = 400;
            res.set_content("{\"error\":\"name y node_id requeridos\"}", "application/json");
            return;
        }
        if (varMgr->addVariable(var)) {
            res.set_content("{\"status\":\"added\"}", "application/json");
        } else {
            res.status = 500;
        }
    });

    svr.Delete(R"(/api/variables/(\d+))", [this](const httplib::Request& req, httplib::Response& res) {
        int id = std::stoi(req.matches[1]);
        if (varMgr->removeVariable(id)) {
            res.set_content("{\"status\":\"deleted\"}", "application/json");
        } else {
            res.status = 500;
        }
    });

    // ===== RF2/RF3/RF4: Clasificacion QR =====
    // Recibe QR del modulo de vision (camara del navegador o Python/OpenCV)
    svr.Post("/api/classify", [this](const httplib::Request& req, httplib::Response& res) {
        std::string qr_val;
        // Intentar extraer "qr":"valor"
        auto pos = req.body.find("\"qr\":\"");
        if (pos != std::string::npos) {
            pos += 6;
            auto end = req.body.find("\"", pos);
            qr_val = req.body.substr(pos, end - pos);
        } else {
            // Intentar "qr":valor (numero)
            auto pos2 = req.body.find("\"qr\":");
            if (pos2 != std::string::npos) {
                pos2 += 5;
                while (pos2 < req.body.size() && req.body[pos2] == ' ') pos2++;
                auto end2 = req.body.find_first_of(",}", pos2);
                qr_val = req.body.substr(pos2, end2 - pos2);
            }
        }

        if (qr_val.empty()) {
            res.status = 400;
            res.set_content("{\"error\":\"Campo 'qr' requerido\"}", "application/json");
            return;
        }

        std::cout << "[WebServer] POST /api/classify -> QR=" << qr_val << std::endl;
        bool ok = classMgr->processQR(qr_val);
        if (ok) {
            res.set_content(
                "{\"status\":\"processed\",\"qr\":\"" + escapeJson(qr_val) + "\"}",
                "application/json");
        } else {
            res.status = 503;
            res.set_content("{\"error\":\"Sistema ocupado. Reintente.\"}", "application/json");
        }
    });

    // ===== RF5: KPI en tiempo real =====
    svr.Get("/api/kpi", [this](const httplib::Request&, httplib::Response& res) {
        SystemState state = classMgr->getSystemState();
        res.set_content(stateToJson(state), "application/json");
    });

    // ===== RF4: Historial de eventos =====
    svr.Get("/api/events", [this](const httplib::Request& req, httplib::Response& res) {
        int limit = 50;
        if (req.has_param("limit")) {
            try { limit = std::stoi(req.get_param_value("limit")); } catch (...) {}
        }
        auto evList = configMgr->getDb()->getRecentEvents(limit);
        std::string json = "[";
        for (size_t i = 0; i < evList.size(); i++) {
            json += eventToJson(evList[i]);
            if (i + 1 < evList.size()) json += ",";
        }
        json += "]";
        res.set_content(json, "application/json");
    });

    // ===== Red =====
    svr.Get("/api/network", [this](const httplib::Request&, httplib::Response& res) {
        auto cfg = configMgr->getNetworkConfig();
        std::string json =
            "{\"ip_eth\":\"" + cfg.ip_eth + "\""
            ",\"ssid_wifi\":\"" + cfg.ssid_wifi + "\""
            ",\"web_port\":" + std::to_string(cfg.web_port) + "}";
        res.set_content(json, "application/json");
    });

    // ===== Logs del Sistema =====
    svr.Get("/api/logs", [this](const httplib::Request& req, httplib::Response& res) {
        int limit = 50;
        if (req.has_param("limit")) {
            try { limit = std::stoi(req.get_param_value("limit")); } catch (...) {}
        }
        auto logs = configMgr->getDb()->getRecentSystemLogs(limit);
        std::string json = "[";
        for (size_t i = 0; i < logs.size(); i++) {
            json += "{\"id\":" + std::to_string(logs[i].id) +
                    ",\"timestamp\":\"" + escapeJson(logs[i].timestamp) + "\"" +
                    ",\"level\":\"" + escapeJson(logs[i].level) + "\"" +
                    ",\"message\":\"" + escapeJson(logs[i].message) + "\"}";
            if (i + 1 < logs.size()) json += ",";
        }
        json += "]";
        res.set_content(json, "application/json");
    });

    // ===== Consola Interactiva del PLC =====
    svr.Post("/api/console", [this](const httplib::Request& req, httplib::Response& res) {
        auto extract = [&](const std::string& key) -> std::string {
            std::string search = "\"" + key + "\":\"";
            auto pos = req.body.find(search);
            if (pos == std::string::npos) return "";
            pos += search.size();
            auto end = req.body.find("\"", pos);
            return req.body.substr(pos, end - pos);
        };

        std::string cmd = extract("cmd");
        if (cmd.empty()) {
            res.status = 400;
            res.set_content("{\"error\":\"Comando vacio\"}", "application/json");
            return;
        }

        std::string response_msg = "";
        configMgr->getDb()->logSystem("INFO", "Comando de consola ejecutado: " + cmd);

        if (cmd.substr(0, 3) == "qr ") {
            std::string qr_val = cmd.substr(3);
            bool ok = classMgr->processQR(qr_val);
            if (ok) response_msg = "QR [" + qr_val + "] procesado.";
            else response_msg = "Sistema ocupado.";
        }
        else if (cmd == "reconnect") {
            auto cfg = configMgr->getOpcConfig();
            opcMgr->disconnect();
            if (cfg.enabled) {
                if (opcMgr->connect(cfg.endpoint, cfg.timeout_ms)) {
                    varMgr->loadAndSubscribeAll();
                    response_msg = "Reconexion exitosa.";
                } else {
                    response_msg = "Fallo reconexion.";
                }
            } else {
                response_msg = "OPC deshabilitado.";
            }
        }
        else if (cmd.substr(0, 6) == "write ") {
            std::stringstream ss(cmd.substr(6));
            std::string var_name, var_val;
            ss >> var_name >> var_val;
            
            auto vars = varMgr->getAllVariables();
            bool found = false;
            for (const auto& v : vars) {
                if (v.name == var_name) {
                    found = true;
                    if (opcMgr->writeVariable(v, var_val)) {
                        response_msg = "Escrito " + var_val + " en " + var_name + " exitosamente.";
                        configMgr->getDb()->logSystem("INFO", response_msg);
                    } else {
                        response_msg = "Fallo al escribir en " + var_name + ". Verifique conexion.";
                        configMgr->getDb()->logSystem("ERROR", response_msg);
                    }
                    break;
                }
            }
            if (!found) {
                response_msg = "Variable " + var_name + " no encontrada.";
            }
        }
        else if (cmd == "status") {
            SystemState st = classMgr->getSystemState();
            std::stringstream ss;
            ss << "STATUS: Motor=" << (st.motor_running ? "ON" : "OFF")
               << " (Speed=" << st.motor_speed << " RPM)"
               << " | P1=" << (st.piston1_active ? "ACT" : "off")
               << " | P2=" << (st.piston2_active ? "ACT" : "off")
               << " | Cat1=" << st.count_cat1
               << " Cat2=" << st.count_cat2
               << " Cat3=" << st.count_cat3
               << " | FSM=" << st.fsm_state;
            response_msg = ss.str();
            configMgr->getDb()->logSystem("INFO", response_msg);
        }
        else {
            response_msg = "Comando no reconocido. Comandos validos: 'qr <val>', 'reconnect', 'write <var> <val>', 'status'.";
        }

        res.set_content("{\"response\":\"" + escapeJson(response_msg) + "\"}", "application/json");
    });
}

// ============================================================
// Start / Stop
// ============================================================
void WebServer::start(int port) {
    if (running) return;
    running = true;
    server_thread = std::thread([this, port]() {
#ifdef CPPHTTPLIB_OPENSSL_SUPPORT
        std::cout << "[WebServer] HTTPS escuchando en 0.0.0.0:" << port << std::endl;
#else
        std::cout << "[WebServer] HTTP escuchando en 0.0.0.0:" << port << std::endl;
#endif
        svr.listen("0.0.0.0", port);
    });
}

void WebServer::stop() {
    if (running) {
        svr.stop();
        if (server_thread.joinable()) server_thread.join();
        running = false;
        std::cout << "[WebServer] Detenido." << std::endl;
    }
}
