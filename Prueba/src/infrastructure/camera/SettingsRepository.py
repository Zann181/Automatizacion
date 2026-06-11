import json
from sqlalchemy.orm import Session
from src.database.models import CameraSettings

class SettingsRepository:
    """CRUD operations for CameraSettings stored in SQLite.
    Provides async-friendly methods that internally run DB operations in a thread pool.
    Only a single row is expected; if none exists defaults are created.
    """
    def __init__(self, db: Session):
        self.db = db

    def get_settings(self) -> dict:
        settings = self.db.query(CameraSettings).first()
        if not settings:
            settings = CameraSettings()
            self.db.add(settings)
            self.db.commit()
            self.db.refresh(settings)
        return {
            "motor_off_duration": float(settings.motor_off_duration),
            "cat1_duration": float(settings.cat1_duration),
            "cat2_duration": float(settings.cat2_duration),
            "cat3_duration": float(settings.cat3_duration),
            "auto_execute": bool(int(settings.auto_execute)),
        }

    def update_settings(self, payload: dict) -> dict:
        settings = self.db.query(CameraSettings).first()
        if not settings:
            settings = CameraSettings()
            self.db.add(settings)
        for key, value in payload.items():
            if hasattr(settings, key):
                if isinstance(value, bool):
                    val_str = "1" if value else "0"
                else:
                    val_str = str(value)
                setattr(settings, key, val_str)
        self.db.commit()
        self.db.refresh(settings)
        return {
            "motor_off_duration": float(settings.motor_off_duration),
            "cat1_duration": float(settings.cat1_duration),
            "cat2_duration": float(settings.cat2_duration),
            "cat3_duration": float(settings.cat3_duration),
            "auto_execute": bool(int(settings.auto_execute)),
        }
