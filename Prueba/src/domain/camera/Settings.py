from dataclasses import dataclass
from typing import Dict

@dataclass
class Settings:
    """Configurable parameters for the camera‑PLC interaction.
    All values are in seconds unless otherwise noted.
    """
    motor_off_duration: float = 5.0  # time motor stays OFF after ACTIVE detection
    cat1_duration: float = 2.0      # advance seconds for category 1
    cat2_duration: float = 3.0      # advance seconds for category 2
    cat3_duration: float = 0.0      # advance seconds for category 3 (no move)
    auto_execute: bool = True       # whether to automatically send PLC commands

    def as_dict(self) -> Dict[str, float|bool]:
        return {
            "motor_off_duration": self.motor_off_duration,
            "cat1_duration": self.cat1_duration,
            "cat2_duration": self.cat2_duration,
            "cat3_duration": self.cat3_duration,
            "auto_execute": self.auto_execute,
        }
