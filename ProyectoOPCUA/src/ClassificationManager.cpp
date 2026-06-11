#include "ClassificationManager.h"
#include <iostream>
#include <sstream>
#include <iomanip>
#include <ctime>
#include <chrono>
#include <stdexcept>

// ============================================================
// Constructor / Destructor
// ============================================================
ClassificationManager::ClassificationManager(DatabaseManager* db, OPCManager* opc)
    : db(db), opc(opc),
      fsm_state(State::IDLE),
      motor_running(false),
      piston1_active(false),
      piston2_active(false),
      motor_speed_rpm(0.0)
{
    std::cout << "[ClassMgr] Inicializado. Esperando eventos QR." << std::endl;
}

ClassificationManager::~ClassificationManager() {
    // Esperar hilo de actuacion si esta activo
    if (actuator_thread.joinable()) {
        actuator_thread.join();
    }
}

// ============================================================
// Punto de entrada principal — RF2, RF3, RF4
// ============================================================
bool ClassificationManager::processQR(const std::string& qr_data) {
    // Evitar reentrada: un solo evento a la vez
    std::unique_lock<std::mutex> lock(process_mutex, std::try_to_lock);
    if (!lock.owns_lock()) {
        std::cerr << "[ClassMgr] Evento ignorado: sistema ocupado procesando otro QR." << std::endl;
        return false;
    }

    auto t_start = std::chrono::high_resolution_clock::now();

    std::cout << "\n[ClassMgr] === Nuevo evento QR: [" << qr_data << "] ===" << std::endl;

    // --- PASO 1: PARAR MOTOR (RF2) ---
    fsm_state = State::DETECTING;
    std::cout << "[ClassMgr] FSM: DETECTING -> comandando parada de motor..." << std::endl;

    bool motor_stopped = writeMotorState(false); // Motor_State = false
    if (!motor_stopped) {
        std::cerr << "[ClassMgr] ADVERTENCIA: No se pudo escribir Motor_State=false. Continuando igual." << std::endl;
        db->logSystem("ERROR", "No se pudo detener el motor en el PLC: error de conexion.");
    } else {
        db->logSystem("INFO", "Banda detenida para clasificacion (Motor_State=false).");
    }
    motor_running = false;
    fsm_state = State::STOPPED;

    auto t_stop = std::chrono::high_resolution_clock::now();
    auto ms_stop = std::chrono::duration_cast<std::chrono::milliseconds>(t_stop - t_start).count();
    std::cout << "[ClassMgr] FSM: STOPPED. Latencia parada OPC-UA: " << ms_stop << "ms" << std::endl;

    // --- PASO 2: CLASIFICAR QR (RF2) ---
    fsm_state = State::CLASSIFYING;
    Categoria cat = classifyQR(qr_data);
    std::string cat_str = std::to_string(static_cast<int>(cat));

    std::string result_str;
    switch (cat) {
        case Categoria::UNO:  result_str = "piston1"; break;
        case Categoria::DOS:  result_str = "piston2"; break;
        case Categoria::TRES: result_str = "pass";    break;
        default:              result_str = "pass";    break;
    }
    std::cout << "[ClassMgr] FSM: CLASSIFYING -> Cat=" << cat_str << " Result=" << result_str << std::endl;

    // --- PASO 3: REGISTRAR EVENTO — RF4 (ISO 8601) ---
    ClassificationEvent event;
    event.timestamp = getISOTimestamp();
    event.qr_data   = qr_data;
    event.categoria = static_cast<int>(cat);
    event.result    = result_str;

    if (!db->logClassificationEvent(event)) {
        std::cerr << "[ClassMgr] ERROR: No se pudo registrar evento en DB (RNF3)." << std::endl;
        // No abortar: continuar con el control fisico
    }

    // --- PASO 4: REINICIAR MOTOR (RF3) ---
    bool motor_started = writeMotorState(true); // Motor_State = true
    if (!motor_started) {
        std::cerr << "[ClassMgr] ADVERTENCIA: No se pudo escribir Motor_State=true." << std::endl;
        db->logSystem("ERROR", "No se pudo arrancar el motor en el PLC: error de conexion.");
    } else {
        db->logSystem("INFO", "Banda arrancada despues de clasificacion (Motor_State=true).");
    }
    motor_running = true;
    fsm_state = State::RUNNING;

    auto t_running = std::chrono::high_resolution_clock::now();
    auto ms_total = std::chrono::duration_cast<std::chrono::milliseconds>(t_running - t_start).count();
    std::cout << "[ClassMgr] FSM: RUNNING. Latencia total ciclo: " << ms_total << "ms (limite: 500ms)" << std::endl;

    // --- PASO 5: PROGRAMAR ACTUACION DE PISTON (RF3, asincronico) ---
    schedulePistonActuation(cat);

    // Liberar FSM (el hilo de piston trabaja en background)
    fsm_state = State::IDLE;
    return true;
}

// ============================================================
// Clasificacion del QR (RF2)
// C in {1, 2, 3, empty}
// ============================================================
Categoria ClassificationManager::classifyQR(const std::string& qr_data) const {
    // Intentar parsear como entero
    try {
        int val = std::stoi(qr_data);
        switch (val) {
            case 1: return Categoria::UNO;
            case 2: return Categoria::DOS;
            case 3: return Categoria::TRES;
            default: return Categoria::OTRO; // Cualquier otro entero
        }
    } catch (...) {
        // No es un numero: categoria invalida (empty set)
        return Categoria::OTRO;
    }
}

// ============================================================
// Temporizacion asincronico de pistones (RF3)
// Cat 1: esperar 2.0s -> activar Piston1
// Cat 2: esperar 4.0s -> activar Piston2
// Cat 3, otro: omitir
// ============================================================
void ClassificationManager::schedulePistonActuation(Categoria cat) {
    if (cat == Categoria::TRES || cat == Categoria::OTRO) {
        std::cout << "[ClassMgr] Actuacion omitida (cat=" << static_cast<int>(cat) << ": dejar pasar)." << std::endl;
        return;
    }

    // Esperar que el hilo anterior termine
    if (actuator_thread.joinable()) {
        actuator_thread.join();
    }

    int piston_num   = (cat == Categoria::UNO) ? 1 : 2;
    double delay_sec = (cat == Categoria::UNO) ? 2.0 : 4.0;

    std::cout << "[ClassMgr] Piston" << piston_num
              << " programado en " << delay_sec << "s (hilo independiente)." << std::endl;

    // Lanzar hilo separado para no bloquear la FSM principal
    actuator_thread = std::thread(
        &ClassificationManager::actuatePiston, this, piston_num, delay_sec
    );
    actuator_thread.detach(); // No bloquear; se auto-limpia
}

void ClassificationManager::actuatePiston(int piston_num, double delay_seconds) {
    // Esperar delta t (RF3: 2.0s o 4.0s)
    auto delay_ms = static_cast<int>(delay_seconds * 1000);
    std::cout << "[ClassMgr] [Hilo Piston" << piston_num << "] Esperando " << delay_seconds << "s..." << std::endl;
    std::this_thread::sleep_for(std::chrono::milliseconds(delay_ms));

    // Activar piston via OPC-UA
    std::string var_name = "Piston" + std::to_string(piston_num);
    auto var_opt = getVarByName(var_name);

    if (var_opt.has_value()) {
        bool ok = opc->writeVariable(var_opt.value(), "1"); // Boolean true
        if (ok) {
            std::cout << "[ClassMgr] [Hilo Piston" << piston_num << "] ACTIVADO via OPC-UA." << std::endl;
            db->logSystem("INFO", "Piston" + std::to_string(piston_num) + " ACTIVADO via OPC-UA.");
        } else {
            std::cerr << "[ClassMgr] [Hilo Piston" << piston_num << "] ERROR escribiendo OPC-UA." << std::endl;
            db->logSystem("ERROR", "No se pudo activar Piston" + std::to_string(piston_num) + " en el PLC (Fallo de conexion).");
        }
        if (piston_num == 1) piston1_active = true;
        else                 piston2_active = true;
    } else {
        std::cerr << "[ClassMgr] Variable " << var_name << " no encontrada en DB." << std::endl;
        db->logSystem("WARN", "Variable " + var_name + " no encontrada en la base de datos.");
        if (piston_num == 1) piston1_active = true; // Simular localmente
        else                 piston2_active = true;
    }

    // Pulso: mantener activo 500ms y desactivar
    std::this_thread::sleep_for(std::chrono::milliseconds(500));

    if (var_opt.has_value()) {
        bool ok = opc->writeVariable(var_opt.value(), "0"); // Boolean false
        if (ok) {
            db->logSystem("INFO", "Piston" + std::to_string(piston_num) + " DESACTIVADO.");
        } else {
            db->logSystem("ERROR", "No se pudo desactivar Piston" + std::to_string(piston_num) + " en el PLC (Fallo de conexion).");
        }
    }
    if (piston_num == 1) piston1_active = false;
    else                 piston2_active = false;

    std::cout << "[ClassMgr] [Hilo Piston" << piston_num << "] DESACTIVADO." << std::endl;
}

// ============================================================
// Escritura de Motor_State en PLC via OPC-UA (RF2, RF3)
// ============================================================
bool ClassificationManager::writeMotorState(bool running) {
    if (!opc->isConnected()) {
        std::cerr << "[ClassMgr] OPC-UA no conectado. Motor_State no enviado." << std::endl;
        return false;
    }
    auto var_opt = getVarByName("Motor_State");
    if (!var_opt.has_value()) {
        std::cerr << "[ClassMgr] Variable Motor_State no encontrada en DB." << std::endl;
        return false;
    }
    std::string val = running ? "1" : "0";
    return opc->writeVariable(var_opt.value(), val);
}

// ============================================================
// refreshOpcState — Lee Motor_Speed del PLC via OPC-UA (RF5)
// Llamado periodicamente desde main.cpp (cada ~800ms)
// ============================================================
void ClassificationManager::refreshOpcState() {
    if (!opc->isConnected()) return;

    auto var_opt = getVarByName("Motor_Speed");
    if (!var_opt.has_value()) return;

    double speed = opc->readFloat(var_opt.value());
    if (speed >= 0.0) {
        motor_speed_rpm.store(speed);
    }
}

// ============================================================
// Estado del sistema para /api/kpi (RF5)
// ============================================================
SystemState ClassificationManager::getSystemState() {
    // Base: conteos desde DB
    SystemState state = db->getSystemState();

    // Superponer estado en tiempo real de OPC (pistones y motor)
    state.motor_running  = motor_running.load();
    state.piston1_active = piston1_active.load();
    state.piston2_active = piston2_active.load();
    state.motor_speed    = motor_speed_rpm.load();
    state.fsm_state      = getFsmStateStr();

    return state;
}

std::string ClassificationManager::getFsmStateStr() const {
    switch (fsm_state.load()) {
        case State::IDLE:         return "IDLE";
        case State::DETECTING:    return "DETECTING";
        case State::STOPPED:      return "STOPPED";
        case State::CLASSIFYING:  return "CLASSIFYING";
        case State::RUNNING:      return "RUNNING";
        default:                  return "UNKNOWN";
    }
}

// ============================================================
// Helpers
// ============================================================
// Timestamp ISO 8601 (RF4)
std::string ClassificationManager::getISOTimestamp() const {
    auto now = std::chrono::system_clock::now();
    std::time_t t = std::chrono::system_clock::to_time_t(now);
    std::tm tm_utc;
#ifdef _WIN32
    gmtime_s(&tm_utc, &t);
#else
    gmtime_r(&t, &tm_utc);
#endif
    std::ostringstream oss;
    oss << std::put_time(&tm_utc, "%Y-%m-%dT%H:%M:%SZ");
    return oss.str();
}

// Buscar variable por nombre en la DB
std::optional<VariableOpc> ClassificationManager::getVarByName(const std::string& name) {
    auto vars = db->getAllVariables();
    for (const auto& v : vars) {
        if (v.name == name) return v;
    }
    return std::nullopt;
}
