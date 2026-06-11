import enum

class Category(enum.Enum):
    """Detection categories used by the camera subsystem.
    - ACTIVE: triggers motor off/on sequence.
    - ONE, TWO, THREE: trigger advance commands with configurable durations.
    """
    ACTIVE = "active"
    ONE = 1
    TWO = 2
    THREE = 3
