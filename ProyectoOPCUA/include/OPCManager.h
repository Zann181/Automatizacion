#pragma once
#include <open62541.h>
#include <string>
#include <atomic>
#include <thread>
#include <mutex>
#include <map>
#include "models/VariableOpc.h"

class OPCManager {
private:
    UA_Client* client;
    std::atomic<bool> is_connected;
    std::atomic<bool> running;
    std::thread client_thread;
    std::mutex mtx;

    struct SubInfo {
        UA_UInt32 subId;
        UA_UInt32 monId;
    };
    std::map<int, SubInfo> subscriptions;

    void runClientLoop();

public:
    OPCManager();
    ~OPCManager();

    bool connect(const std::string& endpoint, int timeout_ms);
    void disconnect();
    bool isConnected() const;

    bool subscribeVariable(const VariableOpc& var);
    bool unsubscribeVariable(int var_id);
    bool writeVariable(const VariableOpc& var, const std::string& value);

    // Lectura sincrona de un valor Float desde el PLC (para Motor_Speed, RF5)
    // Retorna el valor, o -1.0 si la lectura falla.
    double readFloat(const VariableOpc& var);
};
