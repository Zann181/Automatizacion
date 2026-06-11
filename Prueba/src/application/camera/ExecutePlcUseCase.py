import asyncio
from datetime import datetime

from src.domain.camera.DetectionResult import DetectionResult
from src.domain.camera.Settings import Settings
from src.infrastructure.camera.PlcRepository import PlcRepository
from src.infrastructure.camera.SettingsRepository import SettingsRepository

class ExecutePlcUseCase:
    """Orchestrates PLC actions based on a detection result.
    Uses the stored Settings (from the DB) to determine timings.
    """
    def __init__(self):
        self.plc_repo = PlcRepository()

    async def __call__(self, detection: DetectionResult):
        # Load current settings (fallback to defaults if missing)
        from src.database.models import get_db
        from src.infrastructure.camera.SettingsRepository import SettingsRepository
        with get_db() as db:
            repo = SettingsRepository(db)
            settings_data = repo.get_settings()
        if settings_data:
            settings = Settings(**settings_data)
        else:
            settings = Settings()
        # ACTIVE handling (motor off/on sequence)
        if detection.category == "active" or detection.category == "ACTIVE":
            await self.plc_repo.set_motor_state(False)
            await asyncio.sleep(settings.motor_off_duration)
            await self.plc_repo.set_motor_state(True)
            return {"action": "motor_cycle", "duration": settings.motor_off_duration}
        # Numeric category handling (advance command)
        try:
            cat = int(detection.category)
        except (ValueError, TypeError):
            # Unknown category – no action
            return {"action": "none"}
        if cat == 1:
            await self.plc_repo.advance(settings.cat1_duration)
            return {"action": "advance", "seconds": settings.cat1_duration}
        if cat == 2:
            await self.plc_repo.advance(settings.cat2_duration)
            return {"action": "advance", "seconds": settings.cat2_duration}
        if cat == 3:
            # continue – no movement
            return {"action": "continue"}
        return {"action": "none"}
