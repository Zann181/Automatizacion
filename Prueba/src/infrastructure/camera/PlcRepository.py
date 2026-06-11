import asyncio
from src import send_signal

class PlcRepository:
    """Wraps PLC command calls.
    Uses the existing `send_signal` async function.
    """
    async def set_motor_state(self, state: bool):
        # command_type for motor state change is assumed to be "motor_speed" with speed 0 or 1?
        # For simplicity we send a dedicated command "motor_state" (to be handled by PLC client).
        try:
            await send_signal('motor_state', value=state)
        except Exception as e:
            # If the command does not exist, fallback to motor_speed 0/1
            speed = 0 if not state else 1
            await send_signal('motor_speed', speed=speed)
        return {'state': state}

    async def advance(self, seconds: float):
        # Assume an "advance" command that moves the motor for given seconds.
        # We'll reuse motor_speed with a temporary speed increase then stop.
        await send_signal('motor_speed', speed=1)
        await asyncio.sleep(seconds)
        await send_signal('motor_speed', speed=0)
        return {'advanced_seconds': seconds}
