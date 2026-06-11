#pragma once
#include <string>
#include <atomic>
#include <mutex>
#include <thread>
#include <functional>
#include "DatabaseManager.h"
#include "OPCManager.h"
#include "models/ConfigModels.h"

/**
 * ClassificationManager — RF2, RF3, RF4
 *
 * Implementa la FSM de clasificacion:
 *   IDLE  -->  DETECTING (llega QR)
 *          -->  STOPPED  (motor detenido por OPC-UA)
 *          -->  CLASSIFYING (se asigna categoria)
 *          -->  RUNNING   (motor reiniciado + piston programado)
 *          -->  IDLE
 *
 * NodeIDs usados (configurables, deben coincidir con el PLC):
 *   Motor_State  ns=2, s=Motor_State  Boolean  (write)
 *   Motor_Speed  ns=2, s=Motor_Speed  Float    (read/subscribe)
 *   Piston1      ns=2, s=Piston1      Boolean  (write)
 *   Piston2      ns=2, s=Piston2      Boolean  (write)
 */
class ClassificationManager {
public:
    // Estados de la FSM
    enum class State { IDLE, DETECTING, STOPPED, CLASSIFYING, RUNNING };

    ClassificationManager(DatabaseManager* db, OPCManager* opc);
    ~ClassificationManager();

    /**
     * Punto de entrada principal (RF2).
     * Llamado cuando el modulo de vision entrega un resultado QR.
     * qr_data: contenido raw del codigo QR (ej: "1", "2", "ABC")
     * Retorna false si el sistema ya esta procesando un evento.
     */
    bool processQR(const std::string& qr_data);

    /**
     * Actualiza el estado del motor/pistones desde OPC (para KPI RF5).
     * Se llama periodicamente desde main o WebServer.
     */
    void refreshOpcState();

    // Lectura del estado actual del sistema (para /api/kpi)
    SystemState getSystemState();

    // Estado FSM actual (string para JSON)
    std::string getFsmStateStr() const;

    // Estadisticas en memoria (complementan los conteos de DB)
    bool  isMotorRunning()  const { return motor_running.load();  }
    bool  isPiston1Active() const { return piston1_active.load(); }
    bool  isPiston2Active() const { return piston2_active.load(); }
    double getMotorSpeed()  const { return motor_speed_rpm.load(); }

private:
    DatabaseManager* db;
    OPCManager*      opc;

    // Estado de la FSM
    std::atomic<State> fsm_state;
    std::mutex         process_mutex; // Evita reentrada durante clasificacion

    // Estado OPC en memoria (RF5 - velocidad y pistones)
    std::atomic<bool>   motor_running;
    std::atomic<bool>   piston1_active;
    std::atomic<bool>   piston2_active;
    std::atomic<double> motor_speed_rpm;

    // Hilo de actuacion de pistones (no bloqueante)
    std::thread actuator_thread;

    // Helpers
    Categoria    classifyQR(const std::string& qr_data) const;
    std::string  getISOTimestamp() const;
    bool         writeMotorState(bool running);
    void         schedulePistonActuation(Categoria cat);
    void         actuatePiston(int piston_num, double delay_seconds);

    // Obtener VariableOpc de la DB por nombre
    std::optional<VariableOpc> getVarByName(const std::string& name);
};
