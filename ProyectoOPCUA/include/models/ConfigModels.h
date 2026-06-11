#pragma once
#include <string>
#include <mutex>

// ===== CONFIGURACION OPC-UA =====
struct OpcConfig {
    int id = 1;
    std::string ip       = "192.168.0.1";
    int         port     = 4840;
    std::string endpoint = "opc.tcp://192.168.0.1:4840";
    int         timeout_ms   = 5000;
    bool        auto_reconnect   = true;
    std::string security_policy  = "None";
    std::string auth_mode        = "Anonymous";
    bool        enabled          = true;
};

// ===== CONFIGURACION DE RED =====
struct NetworkConfig {
    int id = 1;
    std::string iface_eth  = "eth0";
    std::string ip_eth     = "192.168.0.10";
    std::string mask_eth   = "255.255.255.0";
    std::string iface_wifi = "wlan0";
    std::string ssid_wifi  = "PLC_Control";
    std::string pass_wifi  = "123456789";
    int         web_port   = 8080;
};

// ===== CLASIFICACION (RF2, RF3) =====
// Categorias de clasificacion segun requerimiento
// C in {1, 2, 3, empty}
enum class Categoria {
    OTRO = 0,   // QR invalido / no reconocido -> omitir actuacion
    UNO  = 1,   // Activar Piston1 a los 2.0s
    DOS  = 2,   // Activar Piston2 a los 4.0s
    TRES = 3    // Omitir actuacion (dejar pasar)
};

// Resultado de actuacion de un evento
enum class ResultadoActuacion {
    PISTON1 = 1,
    PISTON2 = 2,
    PASS    = 3
};

// ===== EVENTO DE CLASIFICACION (RF4) =====
struct ClassificationEvent {
    int         id        = 0;
    std::string timestamp;    // ISO 8601 (ej: "2026-05-15T17:00:00Z")
    std::string qr_data;      // Contenido raw del QR escaneado
    int         categoria = 0; // 1, 2, 3 o 0 (otro)
    std::string result;        // "piston1", "piston2", "pass"
};

// ===== ESTADO DEL SISTEMA EN TIEMPO REAL (RF5) =====
struct SystemState {
    // Motor
    double motor_speed   = 0.0;    // RPM leidas desde PLC via OPC-UA
    bool   motor_running = false;  // Estado logico motor

    // Pistones
    bool piston1_active = false;
    bool piston2_active = false;

    // Conteos acumulados por categoria (KPI RF5.3)
    int count_cat1  = 0;
    int count_cat2  = 0;
    int count_cat3  = 0;
    int count_otro  = 0;
    int total_classified = 0;

    // Info de ultimo evento
    std::string last_event_time;
    std::string last_qr_data;
    int         last_categoria = -1;

    // Estado de la FSM
    std::string fsm_state = "IDLE"; // IDLE, DETECTING, STOPPED, RUNNING
};

// ===== LOG DEL SISTEMA =====
struct SystemLog {
    int         id = 0;
    std::string timestamp;
    std::string level;     // "INFO", "WARN", "ERROR"
    std::string message;
};
