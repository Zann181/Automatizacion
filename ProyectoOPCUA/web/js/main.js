// ============================================================
// Dashboard Industrial — Cámara + KPI + Eventos
// ============================================================

// ---- Configuración ----
const KPI_INTERVAL  = 800;   // ms — PU-05 (≤1s)
const EVT_INTERVAL  = 2000;  // ms
const QR_COOLDOWN   = 2500;  // ms — evitar doble envío del mismo QR
const SCAN_FPS      = 15;    // fps de escaneo QR (no es el FPS del video)

// ---- Estado global de la cámara ----
let videoStream   = null;
let scanInterval  = null;
let currentFacing = 'environment'; // 'environment'=trasera, 'user'=frontal
let lastQRSent    = '';
let lastQRTime    = 0;
let cooldownTimer = null;
let sessionDetected = 0;
let sessionSent   = 0;
let sessionStart  = null;
let sessionTimerInterval = null;
let lastEventCount = 0;
let activeTab     = 'cam';

// ---- Canvas oculto para análisis de frames ----
const analysisCanvas = document.createElement('canvas');
const analysisCtx    = analysisCanvas.getContext('2d', { willReadFrequently: true });

// ============================================================
// TABS
// ============================================================
function switchTab(name) {
    document.querySelectorAll('.tab-content').forEach(el => el.classList.remove('active'));
    document.querySelectorAll('.tab-btn').forEach(el => el.classList.remove('active'));
    document.getElementById('tab-' + name).classList.add('active');
    document.getElementById('tab-btn-' + name).classList.add('active');
    activeTab = name;
    if (name === 'events') fetchEvents();
    if (name === 'config') { loadOpcConfig(); loadVariables(); }
    if (name === 'terminal') { fetchLogs(); }
}

// ============================================================
// RELOJ
// ============================================================
function updateClock() {
    document.getElementById('clock').textContent = new Date().toTimeString().slice(0, 8);
}
setInterval(updateClock, 1000);
updateClock();

// ============================================================
// DETECCIÓN DE HTTPS (requerido para cámara en móvil)
// ============================================================
function checkSSL() {
    const isSecure = location.protocol === 'https:' || location.hostname === 'localhost';
    if (!isSecure) {
        const warn = document.getElementById('ssl-warning');
        const urlEl = document.getElementById('https-url');
        if (warn) {
            warn.style.display = 'block';
            urlEl.textContent  = 'https://' + location.hostname + ':8443';
        }
    }
}

// ============================================================
// CÁMARA — Activar / Detener / Voltear
// ============================================================
async function startCamera() {
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
        showToast('Tu navegador no soporta acceso a cámara. Usa Chrome/Safari con HTTPS.', 'error');
        return;
    }

    const constraints = {
        video: {
            facingMode: { ideal: currentFacing },
            width:  { ideal: 1280 },
            height: { ideal: 720 },
            frameRate: { ideal: 30, min: 15 }
        },
        audio: false
    };

    try {
        videoStream = await navigator.mediaDevices.getUserMedia(constraints);
    } catch (err) {
        let msg = 'Error al acceder a la cámara.';
        if (err.name === 'NotAllowedError')  msg = 'Permiso de cámara denegado. Acepta el permiso y recarga.';
        if (err.name === 'NotFoundError')    msg = 'No se encontró ninguna cámara en el dispositivo.';
        if (err.name === 'NotReadableError') msg = 'La cámara está en uso por otra app.';
        showToast(msg, 'error');
        return;
    }

    const video = document.getElementById('camera-video');
    video.srcObject = videoStream;
    video.classList.add('active');
    document.getElementById('video-placeholder').style.display = 'none';

    // Detectar la cámara usada
    const track = videoStream.getVideoTracks()[0];
    const settings = track.getSettings();
    const facingLabel = settings.facingMode === 'user' ? 'Frontal' : 'Trasera';
    document.getElementById('stat-cam-facing').textContent = facingLabel;

    // UI
    document.getElementById('btn-cam-start').style.display = 'none';
    document.getElementById('btn-cam-stop').style.display  = '';
    document.getElementById('btn-cam-flip').style.display  = '';
    document.getElementById('cam-live-dot').style.display  = '';

    // Sesión
    sessionDetected = 0; sessionSent = 0;
    sessionStart    = Date.now();
    updateSessionStats();
    sessionTimerInterval = setInterval(updateSessionStats, 1000);

    // Iniciar escaneo QR
    await video.play();
    startQRScan();
}

function stopCamera() {
    if (videoStream) {
        videoStream.getTracks().forEach(t => t.stop());
        videoStream = null;
    }
    stopQRScan();

    const video = document.getElementById('camera-video');
    video.srcObject = null;
    video.classList.remove('active');
    document.getElementById('video-placeholder').style.display = '';
    document.getElementById('btn-cam-start').style.display = '';
    document.getElementById('btn-cam-stop').style.display  = 'none';
    document.getElementById('btn-cam-flip').style.display  = 'none';
    document.getElementById('cam-live-dot').style.display  = 'none';

    clearInterval(sessionTimerInterval);
    clearOverlay();
    document.getElementById('fps-counter').textContent = '-- FPS';
}

async function flipCamera() {
    currentFacing = currentFacing === 'environment' ? 'user' : 'environment';
    stopCamera();
    await startCamera();
}

// ============================================================
// ESCANEO QR (jsQR)
// ============================================================
let frameCount = 0, lastFPSTime = Date.now(), currentFPS = 0;

function startQRScan() {
    stopQRScan(); // limpiar previo
    const interval = Math.round(1000 / SCAN_FPS);
    scanInterval = setInterval(scanFrame, interval);
}

function stopQRScan() {
    if (scanInterval) { clearInterval(scanInterval); scanInterval = null; }
}

function scanFrame() {
    const video = document.getElementById('camera-video');
    if (!video || video.readyState < 2 || !videoStream) return;

    // Calcular FPS
    frameCount++;
    const now = Date.now();
    if (now - lastFPSTime >= 1000) {
        currentFPS = frameCount;
        frameCount = 0;
        lastFPSTime = now;
        document.getElementById('fps-counter').textContent = currentFPS + ' FPS';
    }

    // Capturar frame en canvas oculto
    const w = video.videoWidth, h = video.videoHeight;
    if (!w || !h) return;
    analysisCanvas.width = w; analysisCanvas.height = h;
    analysisCtx.drawImage(video, 0, 0, w, h);

    const imageData = analysisCtx.getImageData(0, 0, w, h);

    // Detectar QR con jsQR
    if (typeof jsQR === 'undefined') return; // jsQR no cargado
    const code = jsQR(imageData.data, w, h, { inversionAttempts: 'dontInvert' });

    if (code) {
        const overlay = document.getElementById('qr-overlay');
        overlay.width = overlay.offsetWidth;
        overlay.height = overlay.offsetHeight;
        const ctx = overlay.getContext('2d');
        drawQRBox(ctx, code.location, w, h, overlay.width, overlay.height);
        onQRDetected(code.data);
    } else {
        clearOverlay();
    }
}

function drawQRBox(ctx, loc, srcW, srcH, dstW, dstH) {
    const sx = dstW / srcW, sy = dstH / srcH;
    ctx.clearRect(0, 0, dstW, dstH);
    ctx.strokeStyle = '#22c55e';
    ctx.lineWidth   = 3;
    ctx.shadowColor = '#22c55e';
    ctx.shadowBlur  = 8;
    ctx.beginPath();
    ctx.moveTo(loc.topLeftCorner.x * sx,     loc.topLeftCorner.y * sy);
    ctx.lineTo(loc.topRightCorner.x * sx,    loc.topRightCorner.y * sy);
    ctx.lineTo(loc.bottomRightCorner.x * sx, loc.bottomRightCorner.y * sy);
    ctx.lineTo(loc.bottomLeftCorner.x * sx,  loc.bottomLeftCorner.y * sy);
    ctx.closePath();
    ctx.stroke();
    ctx.shadowBlur = 0;
}

function clearOverlay() {
    const overlay = document.getElementById('qr-overlay');
    const ctx = overlay.getContext('2d');
    ctx.clearRect(0, 0, overlay.width, overlay.height);
}

// ============================================================
// ACCIÓN AL DETECTAR UN QR
// ============================================================
function onQRDetected(qrData) {
    const now = Date.now();
    sessionDetected++;

    // Actualizar sidebar
    document.getElementById('last-qr-detected').textContent = qrData;
    document.getElementById('last-qr-time').textContent = new Date().toLocaleTimeString();
    const catInfo = getCatInfo(qrData);
    document.getElementById('last-qr-cat').textContent = catInfo.label;
    document.getElementById('last-qr-cat').style.color  = catInfo.color;

    // Flash visual
    const flash = document.getElementById('qr-flash');
    flash.textContent = 'QR: ' + qrData + ' → ' + catInfo.label;
    flash.classList.add('show');
    setTimeout(() => flash.classList.remove('show'), 1200);

    // Cooldown: no re-enviar el mismo QR en 2.5s
    const isNew  = qrData !== lastQRSent;
    const waited = (now - lastQRTime) > QR_COOLDOWN;
    if (!isNew && !waited) return;

    lastQRSent = qrData;
    lastQRTime = now;

    // Auto-enviar al backend
    if (document.getElementById('auto-send').checked) {
        sendQRToBackend(qrData);
        showCooldown();
    }

    updateSessionStats();
}

function getCatInfo(qrData) {
    switch (qrData.trim()) {
        case '1': return { label: 'Categoría 1 → Pistón 1 @ 2s', color: 'var(--cat1)' };
        case '2': return { label: 'Categoría 2 → Pistón 2 @ 4s', color: 'var(--cat2)' };
        case '3': return { label: 'Categoría 3 → Dejar pasar',   color: 'var(--cat3)' };
        default:  return { label: 'Inválido → Dejar pasar',      color: 'var(--otro)' };
    }
}

function showCooldown() {
    const wrap = document.getElementById('cooldown-wrap');
    const bar  = document.getElementById('cooldown-bar');
    wrap.style.display = 'flex';
    bar.style.width = '100%';
    bar.style.transition = 'none';
    requestAnimationFrame(() => {
        bar.style.transition = `width ${QR_COOLDOWN}ms linear`;
        bar.style.width = '0%';
    });
    clearTimeout(cooldownTimer);
    cooldownTimer = setTimeout(() => { wrap.style.display = 'none'; }, QR_COOLDOWN + 100);
}

function updateSessionStats() {
    document.getElementById('stat-detected').textContent = sessionDetected;
    document.getElementById('stat-sent').textContent     = sessionSent;
    if (sessionStart) {
        const elapsed = Math.floor((Date.now() - sessionStart) / 1000);
        const m = Math.floor(elapsed / 60), s = elapsed % 60;
        document.getElementById('stat-time').textContent = m + ':' + String(s).padStart(2, '0');
    }
}

// ============================================================
// ENVIO AL BACKEND
// ============================================================
async function sendQRToBackend(qrData) {
    try {
        const res = await fetch('/api/classify', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ qr: qrData })
        });
        if (res.ok) {
            sessionSent++;
            updateSessionStats();
            showToast('QR "' + qrData + '" → clasificado', 'success');
            setTimeout(fetchEvents, 600);
        } else {
            showToast('Sistema ocupado, reintentando...', 'error');
        }
    } catch (e) {
        showToast('Sin conexión con el servidor', 'error');
    }
}

// ---- Envío manual desde sidebar ----
async function manualSendQR(val) {
    document.getElementById('manual-result').textContent = '⏳ Enviando QR=' + val + '...';
    await sendQRToBackend(val);
    document.getElementById('manual-result').textContent = '✓ Enviado';
    setTimeout(() => { document.getElementById('manual-result').textContent = ''; }, 2000);
}

async function sendManualCustom() {
    const val = document.getElementById('qr-manual-val').value.trim();
    if (!val) return;
    await manualSendQR(val);
    document.getElementById('qr-manual-val').value = '';
}

// ============================================================
// KPI — polling 800ms (PU-05)
// ============================================================
async function fetchKPI() {
    try {
        const res = await fetch('/api/kpi');
        if (!res.ok) throw new Error();
        renderKPI(await res.json());
    } catch { setOpcStatus(false); }
}

function renderKPI(s) {
    document.getElementById('motor-speed').textContent = parseFloat(s.motor_speed || 0).toFixed(1);
    document.getElementById('motor-bar').style.width = Math.min(100, (s.motor_speed / 1500) * 100) + '%';
    const ml = document.getElementById('motor-state-label');
    if (s.motor_running) { ml.textContent = '▶ EN MARCHA'; ml.className = 'kpi-status running'; }
    else                 { ml.textContent = '■ DETENIDO';  ml.className = 'kpi-status'; }

    setPiston(1, s.piston1_active);
    setPiston(2, s.piston2_active);

    document.getElementById('count-cat1').textContent = s.count_cat1 || 0;
    document.getElementById('count-cat2').textContent = s.count_cat2 || 0;
    document.getElementById('count-cat3').textContent = s.count_cat3 || 0;
    document.getElementById('count-otro').textContent = s.count_otro || 0;
    document.getElementById('total-classified').textContent = s.total_classified || 0;

    const mx = Math.max(s.count_cat1, s.count_cat2, s.count_cat3, s.count_otro, 1);
    ['cat1','cat2','cat3','otro'].forEach((c, i) => {
        const vals = [s.count_cat1, s.count_cat2, s.count_cat3, s.count_otro];
        document.getElementById('bar-' + c).style.width = Math.round(vals[i] / mx * 100) + '%';
    });

    const fsm = document.getElementById('fsm-state-text');
    fsm.textContent = s.fsm_state || 'IDLE';
    fsm.style.color = s.fsm_state === 'STOPPED' ? 'var(--amber)' :
                      s.fsm_state === 'CLASSIFYING' ? 'var(--purple)' :
                      s.fsm_state !== 'IDLE' ? 'var(--green)' : '';
    setOpcStatus(true);
}

function setPiston(num, active) {
    const v = document.getElementById('piston' + num + '-visual');
    const l = document.getElementById('piston' + num + '-label');
    const c = document.getElementById('card-p' + num);
    if (active) {
        v.classList.add('active'); l.textContent = '● ACTIVADO'; l.className = 'kpi-status active';
        c.style.borderColor = 'rgba(34,197,94,.4)'; c.style.boxShadow = '0 0 16px rgba(34,197,94,.15)';
    } else {
        v.classList.remove('active'); l.textContent = '● INACTIVO'; l.className = 'kpi-status';
        c.style.borderColor = ''; c.style.boxShadow = '';
    }
}

function setOpcStatus(ok) {
    document.getElementById('opc-dot').className   = 'status-dot ' + (ok ? 'connected' : 'disconnected');
    document.getElementById('opc-status-text').textContent = ok ? 'OPC-UA Conectado' : 'Sin conexión';
    document.getElementById('opc-badge').style.borderColor = ok ? 'rgba(34,197,94,.3)' : 'rgba(239,68,68,.3)';
}

// ============================================================
// EVENTOS — RF4
// ============================================================
async function fetchEvents() {
    try {
        const res = await fetch('/api/events?limit=30');
        if (!res.ok) return;
        renderEvents(await res.json());
    } catch {}
}

function renderEvents(events) {
    const tbody = document.getElementById('events-body');
    if (!events || !events.length) {
        tbody.innerHTML = '<tr><td colspan="5" class="empty-row">Sin eventos aún.</td></tr>';
        lastEventCount = 0; return;
    }
    const isNew = events.length > lastEventCount;
    lastEventCount = events.length;
    tbody.innerHTML = events.map((e, i) => {
        const cc = e.categoria === 1 ? 'cat1' : e.categoria === 2 ? 'cat2' : e.categoria === 3 ? 'cat3' : 'otro';
        const cl = e.categoria === 0 ? '∅ Inválido' : 'Cat. ' + e.categoria;
        const rl = e.result === 'piston1' ? '→ Pistón 1' : e.result === 'piston2' ? '→ Pistón 2' : '→ Dejar pasar';
        return `<tr class="${i === 0 && isNew ? 'event-row-new' : ''}">
            <td class="mono" style="color:var(--text-muted)">${e.id}</td>
            <td class="mono" style="font-size:11px;color:var(--text-secondary)">${e.timestamp}</td>
            <td class="mono"><strong>${esc(e.qr_data)}</strong></td>
            <td><span class="cat-badge ${cc}">${cl}</span></td>
            <td><span class="result-badge ${e.result}">${rl}</span></td>
        </tr>`;
    }).join('');
}

function esc(s) {
    const d = document.createElement('div');
    d.appendChild(document.createTextNode(String(s)));
    return d.innerHTML;
}

// ============================================================
// CONFIG OPC + VARIABLES
// ============================================================
async function loadOpcConfig() {
    try {
        const d = await (await fetch('/api/opc')).json();
        document.getElementById('opc-ip').value       = d.ip       || '';
        document.getElementById('opc-port').value     = d.port     || '';
        document.getElementById('opc-endpoint').value = d.endpoint || '';
        setOpcStatus(d.connected === true);
    } catch { setOpcStatus(false); }
}

async function reconnectOpc() {
    const btn = document.getElementById('btn-reconnect');
    btn.textContent = 'Guardando...'; btn.disabled = true;

    const ip       = document.getElementById('opc-ip').value.trim();
    const port     = parseInt(document.getElementById('opc-port').value.trim(), 10);
    const endpoint = document.getElementById('opc-endpoint').value.trim() ||
                     (ip && port ? `opc.tcp://${ip}:${port}` : '');

    if (!ip || !port) {
        showToast('IP y puerto son obligatorios', 'error');
        btn.textContent = 'Guardar y Reconectar OPC-UA'; btn.disabled = false;
        return;
    }

    try {
        // 1) Guardar configuración en la base de datos
        const saveRes = await fetch('/api/opc', {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ ip, port, endpoint })
        });
        if (!saveRes.ok) throw new Error('Error al guardar');

        showToast('Configuración guardada. Reconectando...', 'success');
        btn.textContent = 'Reconectando...';

        // 2) Reconectar con la nueva config
        await fetch('/api/opc/reconnect', { method: 'POST' });
        showToast('Reconexión OPC-UA completada', 'success');
        setTimeout(loadOpcConfig, 1500);
    } catch {
        showToast('Error al guardar o reconectar', 'error');
    }
    btn.textContent = 'Guardar y Reconectar OPC-UA'; btn.disabled = false;
}

async function loadVariables() {
    try {
        const data = await (await fetch('/api/variables')).json();
        const tbody = document.getElementById('var-table');
        if (!data || !data.length) {
            tbody.innerHTML = '<tr><td colspan="5" class="empty-row">Sin variables.</td></tr>'; return;
        }
        tbody.innerHTML = data.map(v => `<tr>
            <td class="mono" style="color:var(--text-muted)">${v.id}</td>
            <td><strong>${esc(v.name)}</strong></td>
            <td class="mono" style="font-size:12px;color:var(--accent)">${esc(v.node_id)}</td>
            <td style="color:var(--text-secondary)">${v.data_type}</td>
            <td><button onclick="deleteVar(${v.id})" style="background:rgba(239,68,68,.15);color:var(--red);border:1px solid rgba(239,68,68,.3);padding:3px 9px;border-radius:4px;cursor:pointer;font-size:11px;">Eliminar</button></td>
        </tr>`).join('');
    } catch {}
}

async function addVariable() {
    const name = document.getElementById('var-name').value.trim();
    const node = document.getElementById('var-node').value.trim();
    if (!name || !node) { showToast('Nombre y NodeId obligatorios', 'error'); return; }
    try {
        const res = await fetch('/api/variables', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name, node_id: node })
        });
        if (res.ok) {
            showToast('Variable "' + name + '" agregada', 'success');
            document.getElementById('var-name').value = '';
            document.getElementById('var-node').value = '';
            loadVariables();
        }
    } catch { showToast('Sin conexión', 'error'); }
}

async function deleteVar(id) {
    try {
        await fetch('/api/variables/' + id, { method: 'DELETE' });
        showToast('Variable eliminada', 'success');
        loadVariables();
    } catch {}
}

// ============================================================
// TOAST
// ============================================================
function showToast(msg, type = 'success') {
    const t = document.getElementById('toast');
    t.textContent = msg;
    t.className   = 'toast show ' + type;
    setTimeout(() => { t.className = 'toast'; }, 3000);
}

// ============================================================
// INIT
// ============================================================
window.onload = () => {
    checkSSL();
    loadOpcConfig();
    fetchKPI();
    fetchEvents();

    // KPI polling ≤800ms (PU-05)
    setInterval(fetchKPI, KPI_INTERVAL);
    // Eventos cada 2s
    setInterval(fetchEvents, EVT_INTERVAL);
    // Logs cada 2s si está activo el tab terminal
    setInterval(() => { if (activeTab === 'terminal') fetchLogs(); }, 2000);

    console.log('[Dashboard] Listo. KPI polling cada', KPI_INTERVAL, 'ms');
    console.log('[Dashboard] jsQR:', typeof jsQR !== 'undefined' ? 'cargado ✓' : 'NO cargado — ejecuta: make');
};

// ============================================================
// CONSOLA TERMINAL Y LOGS DEL SISTEMA
// ============================================================
async function fetchLogs() {
    try {
        const res = await fetch('/api/logs?limit=30');
        if (!res.ok) return;
        renderLogs(await res.json());
    } catch {}
}

function renderLogs(logs) {
    const container = document.getElementById('logs-container');
    if (!logs || !logs.length) {
        container.innerHTML = '<div class="log-entry INFO"><div class="log-msg">No hay logs en el sistema.</div></div>';
        return;
    }
    container.innerHTML = logs.map(l => {
        const timeStr = l.timestamp.split('T')[1] ? l.timestamp.split('T')[1].slice(0, 8) : l.timestamp;
        return `<div class="log-entry ${l.level}">
            <div class="log-meta">
                <span class="log-level">${l.level}</span>
                <span class="log-time mono">${timeStr}</span>
            </div>
            <div class="log-msg">${esc(l.message)}</div>
        </div>`;
    }).join('');
}

async function sendTerminalCommand() {
    const input = document.getElementById('terminal-input');
    const cmd = input.value.trim();
    if (!cmd) return;
    
    // Añadir línea ingresada a la pantalla
    appendTerminalLine(cmd, 'cmd-input');
    input.value = '';

    try {
        const res = await fetch('/api/console', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ cmd: cmd })
        });
        if (res.ok) {
            const data = await res.json();
            appendTerminalLine(data.response, 'cmd-output');
        } else {
            appendTerminalLine('Error al ejecutar comando en el servidor.', 'error');
        }
    } catch (e) {
        appendTerminalLine('Error de conexion con el servidor.', 'error');
    }
    
    // Recargar logs a la derecha
    fetchLogs();
}

function handleTerminalKey(event) {
    if (event.key === 'Enter') {
        sendTerminalCommand();
    }
}

function appendTerminalLine(text, type = 'info') {
    const screen = document.getElementById('terminal-screen');
    const line = document.createElement('div');
    line.className = 'terminal-line ' + type;
    if (type === 'cmd-input') {
        line.innerHTML = `<span class="prompt">&gt;</span> ${esc(text)}`;
    } else {
        line.innerHTML = esc(text);
    }
    screen.appendChild(line);
    screen.scrollTop = screen.scrollHeight;
}
