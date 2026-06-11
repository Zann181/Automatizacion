import asyncio
from typing import Any

from ..connection.plc_client import PLCClient

class VerificationError(Exception):
    """Raised when a verification check fails."""
    pass

class Verifier:
    """High‑level verification utilities that rely on :class:`PLCClient`.
    Each method performs the write operation (delegated to ``PLCClient``) and
    then reads back the value to ensure the PLC applied the change.
    """

    def __init__(self, client: PLCClient) -> None:
        self.client = client

    async def verify_piston(self, piston_id: int, expected: bool) -> bool:
        state = await self.client.read_pistons()
        actual = state[piston_id - 1]
        if actual != expected:
            raise VerificationError(
                f"Piston {piston_id} verification failed: expected {expected}, got {actual}"
            )
        return True

    async def verify_motor_speed(self, expected: int) -> bool:
        actual = await self.client.read_motor_speed()
        if actual != expected:
            raise VerificationError(
                f"Motor speed verification failed: expected {expected}, got {actual}"
            )
        return True

    async def verify_motor_state(self, expected: bool) -> bool:
        actual = await self.client.read_motor_state()
        if actual != expected:
            raise VerificationError(
                f"Motor state verification failed: expected {expected}, got {actual}"
            )
        return True

# Helper to run a coroutine from sync Flask context
def run_async(coro: Any) -> Any:
    return asyncio.get_event_loop().run_until_complete(coro)
