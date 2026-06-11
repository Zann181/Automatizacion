# -*- coding: utf-8 -*-
"""Top-level package for the modular PLC control system.
It exposes a convenient function `send_signal` that the Flask server can call.
"""

from .connection.plc_client import PLCClient
from .verification.verification import Verifier, VerificationError
from .database.models import init_db, get_db, CommandLog

# Singleton client – created once at import time
plc_client = PLCClient()

async def _ensure_connected():
    await plc_client.connect()

# Public API used by the server routes
async def send_signal(command_type: str, **kwargs):
    """Dispatch a control command to the PLC.
    ``command_type`` can be ``piston1``, ``piston2`` or ``motor_speed``.
    Returns a dict with the outcome and verification result.
    """
    await _ensure_connected()
    verifier = Verifier(plc_client)
    result = {"command": command_type, "sent": None, "verified": None, "status": "FAIL"}
    try:
        if command_type in ("piston1", "piston2"):
            piston_id = 1 if command_type == "piston1" else 2
            value = kwargs.get("value")
            await plc_client.write_piston(piston_id, value)
            await verifier.verify_piston(piston_id, value)
            result["sent"] = str(value)
            result["verified"] = str(value)
        elif command_type == "motor_speed":
            speed = kwargs.get("speed")
            await plc_client.write_motor_speed(speed)
            await verifier.verify_motor_speed(speed)
            result["sent"] = str(speed)
            result["verified"] = str(speed)
        else:
            raise ValueError("Unsupported command_type")
        result["status"] = "SUCCESS"
    except Exception as e:
        result["error"] = str(e)
        raise
    return result
