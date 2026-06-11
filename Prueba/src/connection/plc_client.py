import asyncio
from asyncua import Client, ua
from typing import Tuple

class PLCClient:
    """Encapsulates OPC-UA communication with the Siemens S7‑1200 PLC.
    Provides async methods for reading and writing the specific nodes used in the
    project (two pistons and motor state/speed)."""

    def __init__(self, url: str = "opc.tcp://192.168.0.1:4840") -> None:
        self.url = url
        self._client: Client | None = None

    async def connect(self) -> None:
        """Open an OPC‑UA session. Idempotent – reconnects only if not already.
        """
        if self._client is None:
            self._client = Client(url=self.url)
            await self._client.__aenter__()
        else:
            # already connected
            pass

    async def disconnect(self) -> None:
        """Close the session gracefully."""
        if self._client is not None:
            await self._client.__aexit__(None, None, None)
            self._client = None

    # ---------------------------------------------------------------------
    # Low‑level node helpers
    # ---------------------------------------------------------------------
    def _node(self, node_id: str):
        if self._client is None:
            raise RuntimeError("PLCClient not connected")
        return self._client.get_node(node_id)

    # ---------------------------------------------------------------------
    # Public API – read ----------------------------------------------------
    # ---------------------------------------------------------------------
    async def read_pistons(self) -> Tuple[bool, bool]:
        piston1 = self._node("ns=4;i=2")
        piston2 = self._node("ns=4;i=5")
        val1 = await piston1.read_value()
        val2 = await piston2.read_value()
        return bool(val1), bool(val2)

    async def read_motor_state(self) -> bool:
        node = self._node("ns=4;i=3")
        return bool(await node.read_value())

    async def read_motor_speed(self) -> int:
        node = self._node("ns=4;i=4")
        return int(await node.read_value())

    # ---------------------------------------------------------------------
    # Public API – write ---------------------------------------------------
    # ---------------------------------------------------------------------
    async def write_piston(self, piston_id: int, value: bool) -> None:
        """Write a boolean to piston *piston_id* (1 or 2)."""
        node_map = {1: "ns=4;i=2", 2: "ns=4;i=5"}
        if piston_id not in node_map:
            raise ValueError("piston_id must be 1 or 2")
        node = self._node(node_map[piston_id])
        dv = ua.DataValue(ua.Variant(value, ua.VariantType.Boolean))
        await node.write_value(dv)

    async def write_motor_speed(self, speed: int) -> None:
        node = self._node("ns=4;i=4")
        dv = ua.DataValue(ua.Variant(speed, ua.VariantType.Int16))
        await node.write_value(dv)

    # ---------------------------------------------------------------------
    # Convenience helpers -------------------------------------------------
    # ---------------------------------------------------------------------
    async def toggle_piston(self, piston_id: int) -> bool:
        """Flip the current state of the selected piston and return the new state."""
        current = await self.read_pistons()
        new_val = not current[piston_id - 1]
        await self.write_piston(piston_id, new_val)
        return new_val

    async def set_motor_speed(self, speed: int) -> int:
        await self.write_motor_speed(speed)
        return speed

# Example usage (run only from an async context, not from the Flask server directly)
# async def demo():
#     client = PLCClient()
#     await client.connect()
#     await client.toggle_piston(1)
#     await client.set_motor_speed(1500)
#     await client.disconnect()
