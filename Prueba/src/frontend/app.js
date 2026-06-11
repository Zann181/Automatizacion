// app.js – Frontend logic for PLC control UI

document.addEventListener('DOMContentLoaded', () => {
    const statusBox = document.getElementById('statusBox');
    const piston1Toggle = document.getElementById('piston1');
    const piston2Toggle = document.getElementById('piston2');
    const motorSpeedInput = document.getElementById('motorSpeed');
    const setSpeedBtn = document.getElementById('setSpeedBtn');

    // Helper to display status JSON nicely
    const renderStatus = (data) => {
        const lines = [];
        lines.push(`Piston 1: ${data.piston1 ? '✅ ON' : '❌ OFF'}`);
        lines.push(`Piston 2: ${data.piston2 ? '✅ ON' : '❌ OFF'}`);
        lines.push(`Motor State: ${data.motor_state ? '✅ RUNNING' : '❌ STOPPED'}`);
        lines.push(`Motor Speed: ${data.motor_speed}`);
        statusBox.textContent = lines.join('\n');
        // sync UI controls with fetched state
        piston1Toggle.checked = !!data.piston1;
        piston2Toggle.checked = !!data.piston2;
        motorSpeedInput.value = data.motor_speed;
    };

    // Fetch current PLC status
    const fetchStatus = async () => {
        try {
            const resp = await fetch('/status');
            if (!resp.ok) throw new Error('Status request failed');
            const data = await resp.json();
            renderStatus(data);
        } catch (err) {
            statusBox.textContent = `Error fetching status: ${err.message}`;
        }
    };

    // Send piston command
    const sendPiston = async (id, value) => {
        try {
            const resp = await fetch(`/control/piston/${id}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ value })
            });
            if (!resp.ok) throw new Error('Control request failed');
            await resp.json(); // ignore payload, just refresh status
            await fetchStatus();
        } catch (err) {
            alert(`Error sending piston ${id}: ${err.message}`);
        }
    };

    // Send motor speed command
    const sendMotorSpeed = async (speed) => {
        try {
            const resp = await fetch('/control/motor_speed', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ speed })
            });
            if (!resp.ok) throw new Error('Control request failed');
            await resp.json();
            await fetchStatus();
        } catch (err) {
            alert(`Error setting motor speed: ${err.message}`);
        }
    };

    // Event listeners for UI controls
    piston1Toggle.addEventListener('change', (e) => {
        sendPiston(1, e.target.checked);
    });
    piston2Toggle.addEventListener('change', (e) => {
        sendPiston(2, e.target.checked);
    });
    setSpeedBtn.addEventListener('click', () => {
        const speed = parseInt(motorSpeedInput.value, 10);
        if (isNaN(speed) || speed < 0) {
            alert('Enter a valid non‑negative speed');
            return;
        }
        sendMotorSpeed(speed);
    });

    // Settings UI logic
    const settingsBtn = document.getElementById('settingsBtn');
    const settingsModal = document.getElementById('settingsModal');
    const saveSettingsBtn = document.getElementById('saveSettingsBtn');
    const closeSettingsBtn = document.getElementById('closeSettingsBtn');
    const motorOffInput = document.getElementById('motorOffDuration');
    const cat1Input = document.getElementById('cat1Duration');
    const cat2Input = document.getElementById('cat2Duration');
    const cat3Input = document.getElementById('cat3Duration');
    const autoExecInput = document.getElementById('autoExecute');

    const loadSettings = async () => {
        try {
            const resp = await fetch('/camera/settings');
            if (!resp.ok) throw new Error('Failed to load settings');
            const data = await resp.json();
            motorOffInput.value = data.motor_off_duration;
            cat1Input.value = data.cat1_duration;
            cat2Input.value = data.cat2_duration;
            cat3Input.value = data.cat3_duration;
            autoExecInput.checked = data.auto_execute;
        } catch (err) {
            console.error('Error loading settings:', err);
        }
    };

    const saveSettings = async () => {
        const payload = {
            motor_off_duration: parseFloat(motorOffInput.value),
            cat1_duration: parseFloat(cat1Input.value),
            cat2_duration: parseFloat(cat2Input.value),
            cat3_duration: parseFloat(cat3Input.value),
            auto_execute: autoExecInput.checked ? 1 : 0
        };
        try {
            const resp = await fetch('/camera/settings', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            if (!resp.ok) throw new Error('Failed to save settings');
            await resp.json();
            settingsModal.style.display = 'none';
            await loadSettings(); // refresh UI
        } catch (err) {
            alert('Error saving settings: ' + err.message);
        }
    };

    // Open/close modal handlers
    settingsBtn.addEventListener('click', () => { settingsModal.style.display = 'flex'; loadSettings(); });
    closeSettingsBtn.addEventListener('click', () => { settingsModal.style.display = 'none'; });
    saveSettingsBtn.addEventListener('click', saveSettings);

    // Initial load and periodic refresh
    fetchStatus();
    setInterval(fetchStatus, 5000); // refresh every 5 seconds

    // ----------------------------------------------------
    // Camera and QR Scanner Logic
    // ----------------------------------------------------
    const video = document.getElementById('video');
    const canvas = document.getElementById('scan-canvas');
    const btnCamera = document.getElementById('btn-camera');
    const qrStatus = document.getElementById('qr-status');
    let canvasCtx = null;
    let cameraActive = false;
    let stream = null;
    let scanInterval = null;
    let lastQRSent = '';
    let lastQRTime = 0;
    const QR_COOLDOWN_MS = 2500;

    if (canvas) {
        canvasCtx = canvas.getContext('2d', { willReadFrequently: true });
    }

    const startCamera = async () => {
        try {
            stream = await navigator.mediaDevices.getUserMedia({ 
                video: { facingMode: 'environment' } 
            });
            video.srcObject = stream;
            video.setAttribute('playsinline', true); // required to tell iOS safari we don't want fullscreen
            await video.play();
            cameraActive = true;
            btnCamera.textContent = 'Stop Camera';
            qrStatus.textContent = 'Camera active. Scanning for QR codes...';
            requestAnimationFrame(tick);
        } catch (err) {
            console.error('Error starting camera:', err);
            qrStatus.textContent = 'Error: ' + err.message;
        }
    };

    const stopCamera = () => {
        if (stream) {
            stream.getTracks().forEach(track => track.stop());
        }
        video.srcObject = null;
        cameraActive = false;
        btnCamera.textContent = 'Start Camera';
        qrStatus.textContent = 'Camera stopped.';
        if (canvasCtx) {
            canvasCtx.clearRect(0, 0, canvas.width, canvas.height);
        }
    };

    btnCamera.addEventListener('click', () => {
        if (cameraActive) stopCamera();
        else startCamera();
    });

    const drawRect = (location, color) => {
        drawLine(location.topLeftCorner, location.topRightCorner, color);
        drawLine(location.topRightCorner, location.bottomRightCorner, color);
        drawLine(location.bottomRightCorner, location.bottomLeftCorner, color);
        drawLine(location.bottomLeftCorner, location.topLeftCorner, color);
    };

    const drawLine = (begin, end, color) => {
        canvasCtx.beginPath();
        canvasCtx.moveTo(begin.x, begin.y);
        canvasCtx.lineTo(end.x, end.y);
        canvasCtx.lineWidth = 4;
        canvasCtx.strokeStyle = color;
        canvasCtx.stroke();
    };

    const sendDetection = async (qrData) => {
        try {
            qrStatus.textContent = `Sending category: ${qrData}...`;
            const payload = { category: qrData, confidence: 1.0 };
            const resp = await fetch('/camera/detect', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            if (!resp.ok) throw new Error('Detection endpoint failed');
            const result = await resp.json();
            qrStatus.textContent = `Executed action: ${result.action}`;
            setTimeout(() => { if (cameraActive) qrStatus.textContent = 'Camera active. Scanning for QR codes...'; }, 2000);
            fetchStatus(); // refresh dashboard right away
        } catch (err) {
            qrStatus.textContent = `Error sending detection: ${err.message}`;
        }
    };

    const tick = () => {
        if (!cameraActive) return;

        if (video.readyState === video.HAVE_ENOUGH_DATA) {
            if (canvas.width !== video.videoWidth || canvas.height !== video.videoHeight) {
                canvas.width = video.videoWidth;
                canvas.height = video.videoHeight;
            }
            canvasCtx.drawImage(video, 0, 0, canvas.width, canvas.height);
            const imageData = canvasCtx.getImageData(0, 0, canvas.width, canvas.height);
            
            if (typeof jsQR !== 'undefined') {
                const code = jsQR(imageData.data, imageData.width, imageData.height, {
                    inversionAttempts: "dontInvert",
                });
                
                if (code) {
                    drawRect(code.location, "#FF3B58");
                    const now = Date.now();
                    const qrData = code.data.trim();
                    
                    const isNew = qrData !== lastQRSent;
                    const cooledDown = (now - lastQRTime) > QR_COOLDOWN_MS;
                    
                    if (isNew || cooledDown) {
                        lastQRSent = qrData;
                        lastQRTime = now;
                        sendDetection(qrData);
                    }
                }
            }
        }
        requestAnimationFrame(tick);
    };
});
