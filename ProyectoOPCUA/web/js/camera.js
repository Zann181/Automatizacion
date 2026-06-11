// ============================================================
// camera.js — Módulo de Cámara Industrial (RF1)
//
// Requisitos cubiertos:
//   RF1 : Video stream ≥30FPS / 720p desde dispositivo móvil
//   RF2 : Envía QR detectado a POST /api/classify → FSM
//   HTTPS: Verifica certificado SSL activo (getUserMedia lo requiere)
// ============================================================

// ---- Configuración RF1 (forzar ≥720p y 30fps) ----
const VIDEO_CONSTRAINTS = {
    video: {
        facingMode:  { ideal: 'environment' },  // Cámara trasera
        width:       { min: 1280, ideal: 1280, max: 1920 },
        height:      { min: 720,  ideal: 720,  max: 1080 },
        frameRate:   { min: 15,   ideal: 30,   max: 60   }
    },
    audio: false
};

// ---- Configuración de escaneo ----
const SCAN_INTERVAL_MS = 50;    // ~20 análisis/seg (jsQR es rápido)
const QR_COOLDOWN_MS   = 2500;  // Cooldown entre envíos del mismo QR
const SERVER_PING_MS   = 3000;  // Intervalo de verificación de servidor

// ---- Estado global ----
let videoStream    = null;
let scanTimer      = null;
let serverTimer    = null;
let sessionSent    = 0;
let lastQRSent     = '';
let lastQRTime     = 0;
let currentFacing  = 'environment';
let cameraActive   = false;

// ---- Medición de FPS real ----
let fpsFrameCount  = 0;
let fpsLastTime    = Date.now();
let fpsActual      = 0;

// ---- Canvas oculto para análisis de frames ----
const analysisCanvas = document.createElement('canvas');
const analysisCtx    = analysisCanvas.getContext('2d', { willReadFrequently: true });

// ============================================================
// INIT — Verificar HTTPS y estado del servidor
// ============================================================
window.addEventListener('load', () => {
    checkHTTPS();
    pingServer();
    serverTimer = setInterval(pingServer, SERVER_PING_MS);

    // Prevenir zoom con doble toque en iOS
    document.addEventListener('touchstart', e => {
        if (e.touches.length > 1) e.preventDefault();
    }, { passive: false });
});

// ============================================================
// VERIFICACIÓN DE HTTPS/CERTIFICADO
// ============================================================
function checkHTTPS() {
    const isSecure = location.protocol === 'https:' || location.hostname === 'localhost';
    const dot      = document.getElementById('ssl-dot');
    const text     = document.getElementById('ssl-text');
    const badge    = document.getElementById('ssl-badge');
    const infoText = document.getElementById('ssl-info-text');

    if (isSecure) {
        dot.classList.add('secure');
        badge.classList.add('secure');
        text.textContent  = 'HTTPS ✓';
        infoText.textContent = `Conexión cifrada activa — ${location.host}`;
        document.getElementById('ssl-info-box').style.borderColor = 'rgba(34,197,94,.4)';
    } else {
        dot.classList.add('insecure');
        badge.classList.add('insecure');
        text.textContent  = 'HTTP ✗';
        infoText.textContent =
            'Se requiere HTTPS. Abre: https://' + location.hostname + ':8443/camera.html';
        document.getElementById('ssl-info-box').style.borderColor = 'rgba(239,68,68,.4)';
        showToast('⚠ Abre esta página sobre HTTPS para usar la cámara', 'error', 6000);
    }
}

// ============================================================
// PING AL SERVIDOR (verifica que la RPi responde)
// ============================================================
async function pingServer() {
    const dot  = document.getElementById('server-dot');
    const text = document.getElementById('server-status-text');
    const val  = document.getElementById('server-val');
    try {
        const t0  = performance.now();
        const res = await fetch('/api/kpi', { signal: AbortSignal.timeout(2500) });
        const ms  = Math.round(performance.now() - t0);
        if (res.ok) {
            dot.className  = 'server-dot ok';
            text.textContent = `Raspberry Pi en línea — latencia: ${ms}ms`;
            val.textContent  = ms + 'ms';
        } else {
            throw new Error('HTTP ' + res.status);
        }
    } catch {
        dot.className  = 'server-dot err';
        text.textContent = 'Sin conexión con la Raspberry Pi';
        val.textContent  = '✗';
    }
}

// ============================================================
// CÁMARA — Activar / Detener (toggle)
// ============================================================
async function toggleCamera() {
    if (cameraActive) {
        stopCamera();
    } else {
        await startCamera();
    }
}

async function startCamera() {
    if (!navigator.mediaDevices?.getUserMedia) {
        showToast('Cámara no disponible. Asegúrate de usar HTTPS en Chrome/Safari.', 'error', 5000);
        return;
    }

    // Verificar HTTPS (obligatorio para getUserMedia en móvil)
    if (location.protocol !== 'https:' && location.hostname !== 'localhost') {
        showToast('Se requiere HTTPS para acceder a la cámara.', 'error', 5000);
        return;
    }

    // Actualizar botón — "Iniciando..."
    setBtnState('loading', '⏳', 'Iniciando...');

    try {
        videoStream = await navigator.mediaDevices.getUserMedia(VIDEO_CONSTRAINTS);
    } catch (err) {
        let msg = 'Error al acceder a la cámara.';
        if (err.name === 'NotAllowedError')     msg = 'Permiso de cámara denegado. Pulsa "Permitir" y recarga.';
        if (err.name === 'NotFoundError')       msg = 'No se encontró cámara en el dispositivo.';
        if (err.name === 'NotReadableError')    msg = 'Cámara ocupada por otra aplicación.';
        if (err.name === 'OverconstrainedError')msg = 'Tu cámara no soporta 720p/30fps. Ajustando...';
        showToast(msg, 'error', 5000);
        setBtnState('start', '▶', 'Activar Cámara');

        // Reintentar sin restricciones estrictas
        if (err.name === 'OverconstrainedError') {
            await startCameraFallback();
        }
        return;
    }

    // Conectar stream al elemento <video>
    const video = document.getElementById('video');
    video.srcObject = videoStream;
    await video.play();
    video.classList.add('active');

    cameraActive = true;

    // Obtener resolución y FPS reales del stream
    const track    = videoStream.getVideoTracks()[0];
    const settings = track.getSettings();
    const w = settings.width  || 0;
    const h = settings.height || 0;
    const f = settings.frameRate || 0;

    document.getElementById('resolution-label').textContent =
        `${w}×${h} @ ${Math.round(f)}fps`;
    document.getElementById('res-val').textContent = `${w}×${h}`;
    document.getElementById('top-sub').textContent = `${w}×${h} @ ${Math.round(f)}fps`;

    // Verificar mínimo RF1 (720p)
    if (h < 720) {
        showToast(`Resolución ${w}×${h}. Se recomienda ≥1280×720 para mejor detección.`, 'error', 4000);
    } else {
        showToast(`Cámara activa: ${w}×${h} @ ${Math.round(f)}fps`, 'success');
    }

    // UI
    document.getElementById('cam-placeholder').classList.add('hidden');
    document.getElementById('scan-frame').classList.add('active');
    document.getElementById('btn-flip').style.display = '';
    document.getElementById('last-qr-row').style.display = 'flex';
    setBtnState('stop', '■', 'Detener Cámara');

    // Iniciar análisis de frames
    fpsFrameCount = 0; fpsLastTime = Date.now();
    scanTimer = setInterval(scanFrame, SCAN_INTERVAL_MS);
}

// Fallback sin restricciones estrictas de resolución
async function startCameraFallback() {
    try {
        videoStream = await navigator.mediaDevices.getUserMedia({
            video: { facingMode: { ideal: 'environment' } },
            audio: false
        });
        // Reintentar el flujo completo con este stream
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
        fpsFrameCount = 0; fpsLastTime = Date.now();
        scanTimer = setInterval(scanFrame, SCAN_INTERVAL_MS);
        showToast('Cámara activa en modo compatible (sin restricción de resolución)', 'success');
    } catch (e) {
        showToast('No se pudo acceder a ninguna cámara.', 'error', 5000);
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

// ============================================================
// ESCANEO DE FRAMES (jsQR)
// ============================================================
function scanFrame() {
    const video = document.getElementById('video');
    if (!video || video.readyState < 2 || !videoStream) return;

    // Medir FPS real
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

    analysisCanvas.width = w; analysisCanvas.height = h;
    analysisCtx.drawImage(video, 0, 0, w, h);
    const imageData = analysisCtx.getImageData(0, 0, w, h);

    if (typeof jsQR === 'undefined') return;

    const code = jsQR(imageData.data, w, h, { inversionAttempts: 'dontInvert' });

    if (code) {
        onQRDetected(code.data);
        document.getElementById('scan-frame').classList.add('detected');
    } else {
        document.getElementById('scan-frame').classList.remove('detected');
    }
}

function updateFPSDisplay(fps) {
    const el = document.getElementById('fps-val');
    el.textContent = fps;
    el.className = 'metric-val mono ' +
        (fps >= 25 ? 'fps-good' : fps >= 15 ? 'fps-ok' : 'fps-bad');
}

// ============================================================
// ACCIÓN AL DETECTAR QR
// ============================================================
function onQRDetected(qrData) {
    const now     = Date.now();
    const isNew   = qrData !== lastQRSent;
    const waited  = (now - lastQRTime) > QR_COOLDOWN_MS;

    // Actualizar sidebar "último QR"
    const catInfo = getCatInfo(qrData);
    document.getElementById('last-qr-val').textContent = qrData;
    document.getElementById('last-qr-cat').textContent = catInfo.label;
    document.getElementById('last-qr-row').style.display = 'flex';

    // Popup sobre el scanner
    const popup = document.getElementById('qr-popup');
    document.getElementById('qr-popup-data').textContent = 'QR: ' + qrData;
    document.getElementById('qr-popup-cat').textContent  = catInfo.label;
    popup.classList.add('show');
    setTimeout(() => popup.classList.remove('show'), 1800);

    // Vibración háptica (móviles Android)
    if (navigator.vibrate && (isNew || waited)) {
        navigator.vibrate([50, 30, 50]);
    }

    // Enviar si es nuevo o pasó el cooldown y auto-envío activo
    if ((isNew || waited) && document.getElementById('auto-send').checked) {
        lastQRSent = qrData;
        lastQRTime = now;
        sendQRToServer(qrData);
    }
}

function getCatInfo(qrData) {
    switch (qrData.trim()) {
        case '1': return { label: 'Cat. 1 → Pistón 1 @ 2.0s', color: '#38bdf8' };
        case '2': return { label: 'Cat. 2 → Pistón 2 @ 4.0s', color: '#a78bfa' };
        case '3': return { label: 'Cat. 3 → Dejar pasar',     color: '#22c55e' };
        default:  return { label: 'Inválido → Ignorar',        color: '#6b7280' };
    }
}

// ============================================================
// ENVÍO AL BACKEND (/api/classify)
// ============================================================
async function sendQRToServer(qrData) {
    try {
        const res = await fetch('/api/classify', {
            method:  'POST',
            headers: { 'Content-Type': 'application/json' },
            body:    JSON.stringify({ qr: qrData }),
            signal:  AbortSignal.timeout(3000)
        });

        if (res.ok) {
            sessionSent++;
            document.getElementById('sent-val').textContent = sessionSent;
            showToast(`✓ QR "${qrData}" → clasificado`, 'success', 1800);
        } else {
            const d = await res.json().catch(() => ({}));
            showToast('Sistema ocupado: ' + (d.error || 'reintentando...'), 'error', 2000);
        }
    } catch (e) {
        showToast('Sin conexión con la Raspberry Pi', 'error', 2500);
    }
}

// ============================================================
// TOAST NOTIFICATIONS
// ============================================================
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
