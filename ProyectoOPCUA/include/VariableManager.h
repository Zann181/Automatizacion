#pragma once
#include "DatabaseManager.h"
#include "OPCManager.h"
#include <vector>

class VariableManager {
private:
    DatabaseManager* db;
    OPCManager* opc;

public:
    VariableManager(DatabaseManager* db, OPCManager* opc);
    
    void loadAndSubscribeAll();

    std::vector<VariableOpc> getAllVariables();
    bool addVariable(const VariableOpc& var);
    bool updateVariable(const VariableOpc& var);
    bool removeVariable(int id);
};
