from flask import Flask, request, jsonify, send_from_directory
import os
import sys
import asyncio

# Ensure the parent src package is on the Python path when running this file directly
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.append(BASE_DIR)

# Set static folder to the shared frontend directory (src/frontend)
STATIC_DIR = os.path.abspath(os.path.join(BASE_DIR, 'frontend'))
from src import send_signal, init_db
from src.application.camera.ExecutePlcUseCase import ExecutePlcUseCase
from src.domain.camera.DetectionResult import DetectionResult
from src.database.models import CommandLog, CameraSettings, get_db
from src.infrastructure.camera.SettingsRepository import SettingsRepository

app = Flask(__name__, static_folder=STATIC_DIR, static_url_path='/static')


# Initialize DB on startup
init_db()

# Helper to run async functions from sync context
def run_async(coro):
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)

@app.route('/')
def index():
    # Serve the UI entry point
    return app.send_static_file('index.html')

@app.route('/control/piston/<int:piston_id>', methods=['POST'])
def control_piston(piston_id):
    data = request.get_json()
    if not data or 'value' not in data:
        return jsonify({'error': 'Missing "value" in JSON payload'}), 400
    command_type = f'piston{piston_id}'
    try:
        result = run_async(send_signal(command_type, value=bool(data['value'])))
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/control/motor_speed', methods=['POST'])
def control_motor_speed():
    data = request.get_json()
    if not data or 'speed' not in data:
        return jsonify({'error': 'Missing "speed" in JSON payload'}), 400
    try:
        result = run_async(send_signal('motor_speed', speed=int(data['speed'])))
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/status', methods=['GET'])
def status():
    # Simple status endpoint – reads current values from PLC
    from src.connection.plc_client import PLCClient
    client = PLCClient()
    async def get_status():
        try:
            await client.connect()
        except Exception as conn_err:
            # Return a clear message if PLC is unreachable
            return {
                'piston1': None,
                'piston2': None,
                'motor_state': None,
                'motor_speed': None,
                'error': f'PLC connection failed: {conn_err}'
            }
        pistons = await client.read_pistons()
        motor_state = await client.read_motor_state()
        motor_speed = await client.read_motor_speed()
        await client.disconnect()
        return {
            'piston1': pistons[0],
            'piston2': pistons[1],
            'motor_state': motor_state,
            'motor_speed': motor_speed,
        }
    try:
        status_data = run_async(get_status())
        return jsonify(status_data)
    except Exception as e:
        # Return error info with 200 status so frontend can display it gracefully
        return jsonify({'error': str(e)})

@app.route('/camera/settings', methods=['GET'])
def get_camera_settings():
    from src.infrastructure.camera.SettingsRepository import SettingsRepository
    with get_db() as db:
        repo = SettingsRepository(db)
        return jsonify(repo.get_settings())

@app.route('/camera/settings', methods=['POST'])
def update_camera_settings():
    payload = request.get_json() or {}
    from src.infrastructure.camera.SettingsRepository import SettingsRepository
    with get_db() as db:
        repo = SettingsRepository(db)
        updated = repo.update_settings(payload)
        return jsonify(updated)

@app.route('/camera/detect', methods=['POST'])
def camera_detect():
    data = request.get_json() or {}
    detection = DetectionResult(category=data.get('category'), confidence=data.get('confidence', 0.0))
    result = run_async(ExecutePlcUseCase()(detection))
    return jsonify(result)

if __name__ == '__main__':
    # Run with reloader for development
    cert_path = os.path.join(BASE_DIR, 'certs', 'cert.pem')
    key_path = os.path.join(BASE_DIR, 'certs', 'key.pem')
    app.run(host='0.0.0.0', port=5000, debug=True, ssl_context=(cert_path, key_path))
