#pragma once
#include <string>

struct VariableOpc {
    int id = 0;
    std::string name;
    std::string description;
    std::string node_id; // e.g., "s=Temperatura" or "i=1001"
    int ns_index = 1;
    std::string data_type; // "Float", "Int32", "Boolean", etc.
    std::string unit;
    bool writable = false;
    int scan_rate_ms = 1000;
    bool enabled = true;
};
