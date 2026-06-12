/* ==========================================================================
   DASHBOARD JS: CONTROLADOR PRINCIPAL CLASIFICADOR QR
   ========================================================================== */

const API_BASE = ""; // API Base URL local

// Estado
let isDraggingSlider = false;
let lastServerSpeed = 30;

// Elementos DOM
const plcBanner = document.getElementById("plc-warning-banner");
const plcDot = document.getElementById("plc-dot");
const plcText = document.getElementById("plc-text");
const sheetsDot = document.getElementById("sheets-dot");
const sheetsText = document.getElementById("sheets-text");
const sheetsWarningToast = document.getElementById("sheets-warning-toast");

// Motor y Controles
const motorBtn = document.getElementById("motor-toggle-btn");
const motorLed = document.getElementById("motor-led");
const speedSlider = document.getElementById("speed-slider");
const speedValue = document.getElementById("speed-value");

// Actuadores
const ledC1 = document.getElementById("led-c1");
const ledC2 = document.getElementById("led-c2");
const ledC3 = document.getElementById("led-c3");

// Estadísticas
const statTotal = document.getElementById("stat-total");
const countCat1 = document.getElementById("count-cat1");
const countCat2 = document.getElementById("count-cat2");
const countCat3 = document.getElementById("count-cat3");
const barCat1 = document.getElementById("bar-cat1");
const barCat2 = document.getElementById("bar-cat2");
const barCat3 = document.getElementById("bar-cat3");

// Formulario de Configuración
const settingsForm = document.getElementById("settings-form");
const sensSlider = document.getElementById("sensitivity");
const sensValue = document.getElementById("sensitivity-value");

// Logs
const logsTbody = document.getElementById("logs-tbody");
const clearLogsBtn = document.getElementById("clear-logs-btn");

// Init
window.addEventListener("load", () => {
    // Cargar configuraciones iniciales
    loadSettings();
    
    // Iniciar sondeador de estado
    updateStatus();
    setInterval(updateStatus, 1000);
    
    // Iniciar sondeador de logs
    loadLogs();
    setInterval(loadLogs, 5000);
    
    // Asignar eventos
    setupEventListeners();
});

// Registrar Listeners
function setupEventListeners() {
    // Cambios en slider de velocidad
    speedSlider.addEventListener("input", (e) => {
        isDraggingSlider = true;
        speedValue.textContent = e.target.value;
    });
    
    speedSlider.addEventListener("change", async (e) => {
        isDraggingSlider = false;
        const newSpeed = parseInt(e.target.value);
        await setMotorSpeed(newSpeed);
    });
    
    // Toggle Motor
    motorBtn.addEventListener("click", toggleMotor);
    
    // Cambios en slider de sensibilidad
    sensSlider.addEventListener("input", (e) => {
        sensValue.textContent = e.target.value;
    });
    
    // Formulario de Ajustes
    settingsForm.addEventListener("submit", saveSettings);
    
    // Limpiar logs
    clearLogsBtn.addEventListener("click", clearLogs);
}

// ==========================================================================
// CONSULTAS DE ESTADO API
// ==========================================================================
async function updateStatus() {
    try {
        const res = await fetch(`${API_BASE}/api/status`);
        if (!res.ok) throw new Error("API error");
        const status = await res.json();
        
        // 1. Conexión PLC (Banner Invasivo)
        if (status.plc_connected) {
            plcBanner.classList.add("hidden");
            plcDot.className = "status-dot green";
            plcText.textContent = "PLC: Conectado";
            document.body.classList.remove("plc-disconnected");
            speedSlider.disabled = false;
            motorBtn.disabled = false;
        } else {
            plcBanner.classList.remove("hidden");
            plcDot.className = "status-dot red";
            plcText.textContent = "PLC: Desconectado";
            document.body.classList.add("plc-disconnected");
            speedSlider.disabled = true;
            motorBtn.disabled = true;
        }
        
        // 2. Conexión Google Sheets (Advertencia No Invasiva)
        if (status.sheets_connected) {
            sheetsDot.className = "status-dot green";
            sheetsText.textContent = "Nube: Conectada";
            sheetsWarningToast.classList.add("hidden");
        } else {
            sheetsDot.className = "status-dot red";
            sheetsText.textContent = "Nube: Desconectada";
            // Solo mostrar la advertencia si hay una URL configurada en el servidor
            if (status.has_sheets_url) {
                sheetsWarningToast.classList.remove("hidden");
            } else {
                sheetsText.textContent = "Nube: No Configurada";
                sheetsDot.className = "status-dot amber";
                sheetsWarningToast.classList.add("hidden");
            }
        }
        
        // 3. Estado del Motor
        if (status.motor_state) {
            motorBtn.className = "motor-btn running";
            motorBtn.querySelector(".motor-icon").textContent = "ON";
            motorBtn.querySelector(".motor-btn-text").textContent = "Detener Motor";
            motorLed.className = "motor-led active";
        } else {
            motorBtn.className = "motor-btn stopped";
            motorBtn.querySelector(".motor-icon").textContent = "OFF";
            motorBtn.querySelector(".motor-btn-text").textContent = "Encender Motor";
            motorLed.className = "motor-led inactive";
        }
        
        // 4. Sincronizar slider si el usuario no lo está arrastrando
        if (!isDraggingSlider && lastServerSpeed !== status.motor_speed) {
            lastServerSpeed = status.motor_speed;
            speedSlider.value = status.motor_speed;
            speedValue.textContent = status.motor_speed;
        }
        
        // 5. Estado Actuadores
        updateActuatorLed(ledC1, status.categoria1_state);
        updateActuatorLed(ledC2, status.categoria2_state);
        updateActuatorLed(ledC3, status.categoria3_state);
        
        // Sincronizar checkboxes de las categorías
        document.getElementById("toggle-c1").checked = status.categoria1_state;
        document.getElementById("toggle-c2").checked = status.categoria2_state;
        document.getElementById("toggle-c3").checked = status.categoria3_state;
        
        // 6. Estadísticas
        updateStats(status);
        
    } catch (e) {
        // En caso de caída de API total, tratar como PLC desconectado
        plcBanner.classList.remove("hidden");
        plcDot.className = "status-dot red";
        plcText.textContent = "API: Desconectada";
        sheetsDot.className = "status-dot red";
        sheetsText.textContent = "Nube: Desconectada";
        sheetsWarningToast.classList.add("hidden");
    }
}

function updateActuatorLed(element, state) {
    if (state) {
        element.classList.add("on");
    } else {
        element.classList.remove("on");
    }
}

function updateStats(status) {
    statTotal.textContent = status.total_scans;
    countCat1.textContent = status.cat1_count;
    countCat2.textContent = status.cat2_count;
    countCat3.textContent = status.cat3_count;
    
    // Porcentajes para barras
    const total = status.total_scans || 1; // Evitar división por cero
    barCat1.style.width = `${(status.cat1_count / total) * 100}%`;
    barCat2.style.width = `${(status.cat2_count / total) * 100}%`;
    barCat3.style.width = `${(status.cat3_count / total) * 100}%`;
}

// Enviar Velocidad Motor
async function setMotorSpeed(speed) {
    try {
        const res = await fetch(`${API_BASE}/api/motor/speed`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ speed })
        });
        if (res.ok) {
            showToast(`Velocidad ajustada a ${speed} Hz`, "success");
        } else {
            showToast("Error en API al cambiar velocidad", "error");
        }
    } catch (e) {
        showToast("Error al enviar comando de velocidad", "error");
    }
}

// Toggle Motor
async function toggleMotor() {
    const isRunning = motorBtn.classList.contains("running");
    try {
        const res = await fetch(`${API_BASE}/api/motor/toggle`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ state: !isRunning })
        });
        if (res.ok) {
            showToast(isRunning ? "Motor apagado" : "Motor encendido", "success");
        } else {
            showToast("Error en API al togglear motor", "error");
        }
    } catch (e) {
        showToast("Error al enviar comando del motor", "error");
    }
}

// ==========================================================================
// AJUSTES DEL SISTEMA
// ==========================================================================
async function loadSettings() {
    try {
        const res = await fetch(`${API_BASE}/api/settings`);
        if (!res.ok) throw new Error();
        const settings = await res.json();
        
        // Llenar formulario
        document.getElementById("initial_delay").value = settings.initial_delay || 1.0;
        document.getElementById("cat1_travel_time").value = settings.cat1_travel_time || 2.0;
        document.getElementById("cat1_duration").value = settings.cat1_duration || 2.0;
        document.getElementById("cat2_travel_time").value = settings.cat2_travel_time || 4.0;
        document.getElementById("cat2_duration").value = settings.cat2_duration || 2.0;
        document.getElementById("cat3_travel_time").value = settings.cat3_travel_time || 0.0;
        document.getElementById("cat3_duration").value = settings.cat3_duration || 2.0;
        
        sensSlider.value = settings.sensitivity || 15;
        sensValue.textContent = settings.sensitivity || 15;
        
        document.getElementById("plc_url").value = settings.plc_url || "opc.tcp://192.168.0.1:4840";
        document.getElementById("google_sheets_url").value = settings.google_sheets_url || "";
    } catch (e) {
        showToast("No se pudieron cargar los ajustes de la BD", "error");
    }
}

async function saveSettings(e) {
    e.preventDefault();
    const saveBtn = document.getElementById("save-settings-btn");
    saveBtn.disabled = true;
    saveBtn.textContent = "Guardando...";

    const formData = new FormData(settingsForm);
    const settings = {
        initial_delay: formData.get("initial_delay"),
        cat1_travel_time: formData.get("cat1_travel_time"),
        cat1_duration: formData.get("cat1_duration"),
        cat2_travel_time: formData.get("cat2_travel_time"),
        cat2_duration: formData.get("cat2_duration"),
        cat3_travel_time: formData.get("cat3_travel_time"),
        cat3_duration: formData.get("cat3_duration"),
        sensitivity: sensSlider.value,
        plc_url: formData.get("plc_url"),
        google_sheets_url: formData.get("google_sheets_url")
    };

    try {
        const res = await fetch(`${API_BASE}/api/settings`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(settings)
        });
        if (res.ok) {
            const data = await res.json();
            showToast("Ajustes guardados correctamente", "success");
            // Notificar sobre la conexión a Sheets tras guardar
            if (settings.google_sheets_url.trim() !== "") {
                if (data.sheets_connected) {
                    showToast("Conexión con Google Sheets verificada ✓", "success");
                } else {
                    showToast("⚠️ Falló conexión con Google Sheets (url incorrecta o sin internet)", "warning");
                }
            }
        } else {
            showToast("Error al guardar ajustes", "error");
        }
    } catch (e) {
        showToast("Error de conexión al guardar ajustes", "error");
    } finally {
        saveBtn.disabled = false;
        saveBtn.textContent = "Guardar Parámetros";
        loadSettings(); // Recargar
    }
}

// ==========================================================================
// HISTORIAL DE REPORTES
// ==========================================================================
async function loadLogs() {
    try {
        const res = await fetch(`${API_BASE}/api/logs`);
        if (!res.ok) throw new Error();
        const logs = await res.json();
        
        if (logs.length === 0) {
            logsTbody.innerHTML = `<tr><td colspan="5" class="loading-td">No hay registros de escaneo en la base de datos.</td></tr>`;
            return;
        }
        
        let html = "";
        logs.forEach(log => {
            const date = new Date(log.timestamp).toLocaleString('es-CO');
            const syncBadge = log.synced 
                ? `<span class="sync-badge yes">☁️ Sincronizado</span>` 
                : `<span class="sync-badge no">💾 Local (Pendiente)</span>`;
                
            html += `
                <tr>
                    <td class="mono-cell">${log.id}</td>
                    <td>${date}</td>
                    <td class="mono-cell">${log.qr_data}</td>
                    <td><span class="cat-badge c${log.category}">Categoría ${log.category}</span></td>
                    <td>${syncBadge}</td>
                </tr>
            `;
        });
        logsTbody.innerHTML = html;
    } catch (e) {
        logsTbody.innerHTML = `<tr><td colspan="5" class="loading-td" style="color:var(--danger)">Error al cargar registros del servidor.</td></tr>`;
    }
}

async function clearLogs() {
    if (!confirm("¿Está seguro de que desea vaciar todo el historial de reportes locales? Esta acción no se puede deshacer.")) return;
    
    try {
        const res = await fetch(`${API_BASE}/api/logs/clear`, { method: "POST" });
        if (res.ok) {
            showToast("Historial vaciado correctamente", "success");
            loadLogs();
        } else {
            showToast("Error al limpiar historial", "error");
        }
    } catch (e) {
        showToast("Error al enviar comando para limpiar historial", "error");
    }
}

// ==========================================================================
// UTILERÍA: TOAST NOTIFICATIONS
// ==========================================================================
function showToast(msg, type = "success") {
    const wrap = document.getElementById("toast-wrap");
    const toast = document.createElement("div");
    toast.className = `toast ${type}`;
    toast.textContent = msg;
    wrap.appendChild(toast);
    
    setTimeout(() => {
        toast.style.animation = "toast-out .3s ease forwards";
        setTimeout(() => toast.remove(), 320);
    }, 2800);
}

// ==========================================================================
// SIMULACIÓN DE PRUEBAS DESDE INTERFAZ
// ==========================================================================
async function testScan(category) {
    try {
        const qrData = `MOCK_QR_CAT_${category}_${Math.floor(Date.now() / 1000)}`;
        const res = await fetch(`${API_BASE}/api/notificar_categoria`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ categoria: category, qr_data: qrData })
        });
        if (res.ok) {
            showToast(`Simulación Cat ${category} enviada al servidor`, "success");
            // Recargar logs y estadísticas en breve
            setTimeout(() => {
                loadLogs();
                updateStatus();
            }, 600);
        } else {
            showToast("Error en el servidor al simular escaneo", "error");
        }
    } catch (e) {
        showToast("Error de conexión al simular escaneo", "error");
    }
}

// Control manual de categorías mediante deslizador (switch toggle)
async function toggleCategory(category, state) {
    try {
        const res = await fetch(`${API_BASE}/api/category/toggle`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ category: category, state: state })
        });
        if (res.ok) {
            showToast(`Categoría ${category} cambiada a ${state ? 'ENCENDIDA (True)' : 'APAGADA (False)'}`, "success");
        } else {
            showToast(`Error al cambiar Categoría ${category}`, "error");
            document.getElementById(`toggle-c${category}`).checked = !state;
        }
    } catch (e) {
        showToast("Error de conexión al cambiar la categoría", "error");
        document.getElementById(`toggle-c${category}`).checked = !state;
    }
}
