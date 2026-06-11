from dataclasses import dataclass
from datetime import datetime

@dataclass
class DetectionResult:
    """Result of a camera detection.
    category: int or str representing detected category
    confidence: float confidence score (0-1)
    timestamp: datetime of detection (defaults to now)
    """
    category: int
    confidence: float
    timestamp: datetime = datetime.utcnow()
