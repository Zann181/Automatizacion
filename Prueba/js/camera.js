/* ==========================================================================
   CAMERA JS: CONTROLADOR DE CÁMARA INDUSTRIAL Y ESCANEO QR
   ========================================================================== */

const API_BASE_URL = "";

// Configuración de video (Fuerza 720p y fps altos)
const VIDEO_CONSTRAINTS = {
    video: {
        facingMode:  { ideal: 'environment' },
        width:       { min: 1280, ideal: 1280, max: 1920 },
        height:      { min: 720,  ideal: 720,  max: 1080 },
        frameRate:   { min: 15,   ideal: 30,   max: 60   }
    },
    audio: false
};

// Intervalos
const SCAN_INTERVAL_MS = 60;    // ~16 análisis/seg
const SERVER_PING_MS   = 3000;

// Estado global de la cámara
let videoStream    = null;
let scanTimer      = null;
let serverTimer    = null;
let sessionSent    = 0;
let lastQRSent     = '';
let currentFacing  = 'environment';
let cameraActive   = false;

// Estado de la automatización local
let appSettings    = {};
let isCooldown     = false;
let cooldownTimer  = null;
let isBoxInZone    = false; // Bandera de si la caja entró
let motorIsRunning = true;  // Estado del motor rastreado localmente

// Medición de FPS
let fpsFrameCount  = 0;
let fpsLastTime    = Date.now();
let fpsActual      = 0;

// Canvas de análisis QR
const analysisCanvas = document.createElement('canvas');
const analysisCtx    = analysisCanvas.getContext('2d', { willReadFrequently: true });

// Canvas de análisis de movimiento (Baja resolución para rendimiento)
const motionCanvas = document.createElement('canvas');
motionCanvas.width = 40;
motionCanvas.height = 30;
const motionCtx = motionCanvas.getContext('2d', { willReadFrequently: true });
let prevFrameGray = null;

// ==========================================================================
// CARGAR PÁGINA
// ==========================================================================
window.addEventListener('load', async () => {
    checkHTTPS();
    await fetchSettings();
    pingServer();
    serverTimer = setInterval(pingServer, SERVER_PING_MS);
    
    // Evitar zoom táctil en iOS
    document.addEventListener('touchstart', e => {
        if (e.touches.length > 1) e.preventDefault();
    }, { passive: false });
});

// ==========================================================================
// PETICIONES API
// ==========================================================================
async function fetchSettings() {
    try {
        const res = await fetch(`${API_BASE_URL}/api/settings`);
        if (res.ok) {
            appSettings = await res.json();
            console.log("Ajustes cargados en Cámara:", appSettings);
        }
    } catch (e) {
        console.error("Error cargando ajustes:", e);
    }
}

async function pingServer() {
    const dot  = document.getElementById('server-dot');
    const text = document.getElementById('server-status-text');
    const val  = document.getElementById('server-val');
    try {
        const t0  = performance.now();
        const res = await fetch(`${API_BASE_URL}/api/status`);
        const ms  = Math.round(performance.now() - t0);
        
        if (res.ok) {
            const status = await res.json();
            motorIsRunning = status.motor_state; // Actualizar estado del motor
            
            dot.className  = 'server-dot ok';
            text.textContent = `API en línea — latencia: ${ms}ms`;
            val.textContent  = ms + 'ms';
            val.style.color  = 'var(--accent)';
            
            // Si el motor en el PLC se encendió manualmente, quitar bandera de caja
            if (motorIsRunning && !isCooldown) {
                isBoxInZone = false;
            }
        } else {
            throw new Error();
        }
    } catch {
        dot.className  = 'server-dot err';
        text.textContent = 'Sin conexión con el Servidor API';
        val.textContent  = '✗';
        val.style.color  = 'var(--danger)';
    }
}

function checkHTTPS() {
    const isSecure = location.protocol === 'https:' || location.hostname === 'localhost' || location.hostname === '127.0.0.1';
    const dot      = document.getElementById('ssl-dot');
    const text     = document.getElementById('ssl-text');
    const badge    = document.getElementById('ssl-badge');
    const infoText = document.getElementById('ssl-info-text');

    if (isSecure) {
        dot.classList.add('secure');
        if(badge) badge.classList.add('secure');
        text.textContent  = 'HTTPS ✓';
        infoText.textContent = `Conexión segura/local activa — ${location.host}`;
        document.getElementById('ssl-info-box').style.borderColor = 'rgba(0, 255, 136, 0.4)';
    } else {
        dot.classList.add('insecure');
        if(badge) badge.classList.add('insecure');
        text.textContent  = 'HTTP ✗';
        infoText.textContent = 'Se requiere HTTPS para habilitar la cámara en móviles.';
        document.getElementById('ssl-info-box').style.borderColor = 'rgba(255, 68, 68, 0.4)';
        showToast('⚠ Abre esta página sobre HTTPS para usar la cámara', 'error', 6000);
    }
}

// ==========================================================================
// CONTROL DE CÁMARA
// ==========================================================================
async function toggleCamera() {
    if (cameraActive) {
        stopCamera();
    } else {
        await startCamera();
    }
}

async function startCamera() {
    if (!navigator.mediaDevices?.getUserMedia) {
        showToast('Cámara no disponible. Asegúrate de usar HTTPS.', 'error', 5000);
        return;
    }

    setBtnState('loading', '⏳', 'Iniciando...');
    await fetchSettings(); // Refrescar sensibilidad

    try {
        videoStream = await navigator.mediaDevices.getUserMedia(VIDEO_CONSTRAINTS);
    } catch (err) {
        let msg = 'Error al acceder a la cámara.';
        if (err.name === 'NotAllowedError')     msg = 'Permiso de cámara denegado.';
        if (err.name === 'NotFoundError')       msg = 'No se encontró cámara.';
        if (err.name === 'OverconstrainedError')msg = 'Resolución no soportada. Ajustando...';
        showToast(msg, 'error', 5000);
        setBtnState('start', '▶', 'Activar Cámara');

        if (err.name === 'OverconstrainedError') {
            await startCameraFallback();
        }
        return;
    }

    const video = document.getElementById('video');
    video.srcObject = videoStream;
    await video.play();
    video.classList.add('active');

    cameraActive = true;

    const track    = videoStream.getVideoTracks()[0];
    const settings = track.getSettings();
    const w = settings.width  || 0;
    const h = settings.height || 0;
    const f = settings.frameRate || 0;

    document.getElementById('resolution-label').textContent = `${w}×${h} @ ${Math.round(f)}fps`;
    document.getElementById('res-val').textContent = `${w}×${h}`;

    if (h < 720) {
        showToast(`Resolución baja (${w}×${h}). Se recomienda ≥720p.`, 'warning', 4000);
    } else {
        showToast(`Cámara activa: ${w}×${h}`, 'success');
    }

    document.getElementById('cam-placeholder').classList.add('hidden');
    document.getElementById('scan-frame').classList.add('active');
    document.getElementById('btn-flip').style.display = '';
    document.getElementById('last-qr-row').style.display = 'flex';
    setBtnState('stop', '■', 'Detener Cámara');

    fpsFrameCount = 0; 
    fpsLastTime = Date.now();
    prevFrameGray = null;
    isCooldown = false;
    isBoxInZone = false;
    scanTimer = setInterval(scanFrame, SCAN_INTERVAL_MS);
}

async function startCameraFallback() {
    try {
        videoStream = await navigator.mediaDevices.getUserMedia({
            video: { facingMode: { ideal: currentFacing } },
            audio: false
        });
        const video = document.getElementById('video');
        video.srcObject = videoStream;
        await video.play();
        video.classList.add('active');
        cameraActive = true;
        
        document.getElementById('cam-placeholder').classList.add('hidden');
        document.getElementById('scan-frame').classList.add('active');
        document.getElementById('btn-flip').style.display = '';
        document.getElementById('last-qr-row').style.display = 'flex';
        setBtnState('stop', '■', 'Detener Cámara');
        
        fpsFrameCount = 0; 
        fpsLastTime = Date.now();
        prevFrameGray = null;
        isCooldown = false;
        isBoxInZone = false;
        scanTimer = setInterval(scanFrame, SCAN_INTERVAL_MS);
        showToast('Cámara activa (Modo compatibilidad)', 'success');
    } catch (e) {
        showToast('No se pudo acceder a la cámara.', 'error', 5000);
        setBtnState('start', '▶', 'Activar Cámara');
    }
}

function stopCamera() {
    if (videoStream) {
        videoStream.getTracks().forEach(t => t.stop());
        videoStream = null;
    }
    if (scanTimer) { clearInterval(scanTimer); scanTimer = null; }

    const video = document.getElementById('video');
    video.srcObject = null;
    video.classList.remove('active');

    cameraActive = false;
    document.getElementById('cam-placeholder').classList.remove('hidden');
    document.getElementById('scan-frame').classList.remove('active', 'detected');
    document.getElementById('btn-flip').style.display = 'none';
    document.getElementById('fps-val').textContent   = '--';
    document.getElementById('fps-val').className     = 'metric-val mono';
    document.getElementById('resolution-label').textContent = 'Detenida';
    setBtnState('start', '▶', 'Activar Cámara');
}

async function flipCamera() {
    currentFacing = currentFacing === 'environment' ? 'user' : 'environment';
    stopCamera();
    VIDEO_CONSTRAINTS.video.facingMode = { ideal: currentFacing };
    await startCamera();
}

function setBtnState(state, icon, text) {
    const btn  = document.getElementById('btn-main');
    const iEl  = document.getElementById('btn-main-icon');
    const tEl  = document.getElementById('btn-main-text');
    iEl.textContent = icon;
    tEl.textContent = text;
    if (state === 'stop')    { btn.className = 'ctrl-btn-main stop';    }
    else if (state === 'loading') { btn.className = 'ctrl-btn-main'; btn.disabled = true; setTimeout(() => btn.disabled = false, 4000); }
    else                     { btn.className = 'ctrl-btn-main';         }
}

// ==========================================================================
// DETECCIÓN DE MOVIMIENTO (Caja Entrando)
// ==========================================================================
function detectBoxMovement(video) {
    if (isCooldown) return false;
    
    // Dibujar frame actual en canvas de baja resolución
    motionCtx.drawImage(video, 0, 0, motionCanvas.width, motionCanvas.height);
    const frameData = motionCtx.getImageData(0, 0, motionCanvas.width, motionCanvas.height);
    const pixels = frameData.data;
    
    // Crear buffer en escala de grises
    const currentGray = new Uint8Array(motionCanvas.width * motionCanvas.height);
    for (let i = 0; i < pixels.length; i += 4) {
        // Fórmula de luminancia
        currentGray[i / 4] = 0.299 * pixels[i] + 0.587 * pixels[i+1] + 0.114 * pixels[i+2];
    }
    
    if (prevFrameGray === null) {
        prevFrameGray = currentGray;
        return false;
    }
    
    // Calcular la diferencia absoluta promedio
    let totalDiff = 0;
    for (let i = 0; i < currentGray.length; i++) {
        totalDiff += Math.abs(currentGray[i] - prevFrameGray[i]);
    }
    const avgDiff = totalDiff / currentGray.length;
    
    // Guardar para el siguiente frame
    prevFrameGray = currentGray;
    
    // Sensibilidad mapeada de 1-100 a umbral de diferencia (por defecto: sensibilidad 15)
    // Sensibilidad alta (ej: 90) -> Umbral bajo (sensible)
    // Sensibilidad baja (ej: 10) -> Umbral alto (requiere gran cambio)
    const sensValue = parseInt(appSettings.sensitivity || 15);
    const threshold = Math.max(1.5, (100 - sensValue) * 0.15 + 2.0);
    
    // Si la diferencia supera el umbral, hay movimiento
    if (avgDiff > threshold) {
        console.log(`Movimiento detectado: avgDiff=${avgDiff.toFixed(2)}, umbral=${threshold.toFixed(2)}`);
        return true;
    }
    return false;
}

// ==========================================================================
// PROCESAMIENTO Y ESCANEO DE FRAMES
// ==========================================================================
async function scanFrame() {
    const video = document.getElementById('video');
    if (!video || video.readyState < 2 || !videoStream) return;

    // Medición de FPS
    fpsFrameCount++;
    const now = Date.now();
    if (now - fpsLastTime >= 1000) {
        fpsActual     = fpsFrameCount;
        fpsFrameCount = 0;
        fpsLastTime   = now;
        updateFPSDisplay(fpsActual);
    }

    const w = video.videoWidth, h = video.videoHeight;
    if (!w || !h) return;

    // 1. Detectar si una caja está entrando (Detección de Movimiento)
    if (!isCooldown && !isBoxInZone && motorIsRunning) {
        const motionDetected = detectBoxMovement(video);
        if (motionDetected) {
            isBoxInZone = true;
            // Informar de inmediato al backend para detener el motor
            console.log("Caja detectada entrando. Enviando orden de parada...");
            triggerBoxStop();
        }
    }

    // 2. Escanear código QR si la caja ya entró o si está activo el escaneo
    analysisCanvas.width = w; 
    analysisCanvas.height = h;
    analysisCtx.drawImage(video, 0, 0, w, h);
    const imageData = analysisCtx.getImageData(0, 0, w, h);

    if (typeof jsQR === 'undefined') return;

    const code = jsQR(imageData.data, w, h, { inversionAttempts: 'dontInvert' });

    if (code && code.data.trim() !== '') {
        document.getElementById('scan-frame').classList.add('detected');
        
        // Evitar procesar si estamos en cooldown
        if (!isCooldown) {
            await onQRDetected(code.data);
        }
    } else {
        document.getElementById('scan-frame').classList.remove('detected');
    }
}

function updateFPSDisplay(fps) {
    const el = document.getElementById('fps-val');
    el.textContent = fps;
    el.className = 'metric-val mono ' + (fps >= 25 ? 'fps-good' : fps >= 15 ? 'fps-ok' : 'fps-bad');
}

// Enviar señal de parada inmediata al backend
async function triggerBoxStop() {
    try {
        motorIsRunning = false; // Asumir parado en local
        const res = await fetch(`${API_BASE_URL}/api/box_entered`, { method: 'POST' });
        if (res.ok) {
            showToast("Banda Detenida: Caja detectada", "warning", 1500);
        }
    } catch (e) {
        console.error("Error al enviar señal de parada:", e);
    }
}

// ==========================================================================
// QR DETECTADO Y SECUENCIA DE COOLDOWN
// ==========================================================================
async function onQRDetected(qrData) {
    // Validar categoría numérica (1, 2, 3)
    const val = parseInt(qrData.trim());
    if (isNaN(val) || val < 1 || val > 3) {
        showToast("Código QR inválido (Debe ser categoría 1, 2 o 3)", "error", 2000);
        return;
    }
    
    // Bloquear escáner de inmediato (iniciar Cooldown)
    isCooldown = true;
    isBoxInZone = false;
    prevFrameGray = null; // Reiniciar buffer de movimiento
    
    // Retroalimentación visual
    const catLabel = `Categoría ${val}`;
    document.getElementById('last-qr-val').textContent = qrData;
    document.getElementById('last-qr-cat').textContent = catLabel;
    
    const popup = document.getElementById('qr-popup');
    document.getElementById('qr-popup-data').textContent = 'QR: ' + qrData;
    document.getElementById('qr-popup-cat').textContent  = catLabel;
    popup.classList.add('show');
    setTimeout(() => popup.classList.remove('show'), 2000);
    
    if (navigator.vibrate) {
        navigator.vibrate([100, 50, 100]);
    }
    
    // Notificar al Servidor
    showToast(`✓ Categoría ${val} identificada. Clasificando...`, 'success', 2000);
    await sendQRToServer(val, qrData);
    
    // Calcular tiempo de Cooldown dinámico basado en tiempo de viaje + pistón + holgura
    // Esto asegura que la caja se descarte por completo del sensor antes de volver a armarlo
    let travelTime = 2.0;
    let activeTime = 2.0;
    
    if (val === 1) {
        travelTime = parseFloat(appSettings.cat1_travel_time || 2.0);
        activeTime = parseFloat(appSettings.cat1_duration || 2.0);
    } else if (val === 2) {
        travelTime = parseFloat(appSettings.cat2_travel_time || 4.0);
        activeTime = parseFloat(appSettings.cat2_duration || 2.0);
    } else if (val === 3) {
        travelTime = parseFloat(appSettings.cat3_travel_time || 0.0);
        activeTime = parseFloat(appSettings.cat3_duration || 2.0);
    }
    
    const totalSecs = travelTime + activeTime + 2.5; // Tiempo total de secuencia + 2.5s holgura
    console.log(`Iniciando Cooldown de ${totalSecs}s para Categoría ${val}...`);
    
    // Temporizador para reactivar
    if (cooldownTimer) clearTimeout(cooldownTimer);
    cooldownTimer = setTimeout(() => {
        isCooldown = false;
        console.log("Escáner reactivado (Cooldown completado).");
        showToast("Escáner listo para la siguiente caja", "success", 1500);
    }, totalSecs * 1000);
}

// Enviar datos al Servidor API
async function sendQRToServer(categoria, qrData) {
    try {
        const res = await fetch(`${API_BASE_URL}/api/notificar_categoria`, {
            method:  'POST',
            headers: { 'Content-Type': 'application/json' },
            body:    JSON.stringify({ categoria, qr_data: qrData.toString() })
        });
        if (res.ok) {
            sessionSent++;
            document.getElementById('sent-val').textContent = sessionSent;
        } else {
            showToast('Error al procesar categoría en el Servidor', 'error', 2500);
        }
    } catch (e) {
        showToast('Fallo de conexión al enviar categoría', 'error', 2500);
    }
}

// ==========================================================================
// TOAST NOTIFICATIONS
// ==========================================================================
function showToast(msg, type = 'success', durationMs = 2500) {
    const wrap  = document.getElementById('toast-wrap');
    const toast = document.createElement('div');
    toast.className   = 'toast ' + type;
    toast.textContent = msg;
    wrap.appendChild(toast);
    setTimeout(() => {
        toast.style.animation = 'toast-out .3s ease forwards';
        setTimeout(() => toast.remove(), 320);
    }, durationMs);
}