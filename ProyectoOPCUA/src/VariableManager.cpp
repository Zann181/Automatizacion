#include "VariableManager.h"

VariableManager::VariableManager(DatabaseManager* db, OPCManager* opc)
    : db(db), opc(opc) {}

void VariableManager::loadAndSubscribeAll() {
    auto vars = db->getEnabledVariables();
    for (const auto& v : vars) {
        opc->subscribeVariable(v);
    }
}

std::vector<VariableOpc> VariableManager::getAllVariables() {
    return db->getAllVariables();
}

bool VariableManager::addVariable(const VariableOpc& var) {
    if (db->saveVariable(var)) {
        if (var.enabled) {
            loadAndSubscribeAll();
        }
        return true;
    }
    return false;
}

bool VariableManager::updateVariable(const VariableOpc& var) {
    auto old_var = db->getVariable(var.id);
    if (!old_var) return false;

    if (db->updateVariable(var)) {
        opc->unsubscribeVariable(var.id);
        if (var.enabled) {
            opc->subscribeVariable(var);
        }
        return true;
    }
    return false;
}

bool VariableManager::removeVariable(int id) {
    opc->unsubscribeVariable(id);
    return db->deleteVariable(id);
}

