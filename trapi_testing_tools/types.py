from enum import Enum
from typing import Literal


class LogLevel(Enum):
    ERROR = "ERROR"
    WARNING = "WARNING"
    INFO = "INFO"
    DEBUG = "DEBUG"


class TestType(Enum):
    asset = "asset"
    case = "case"
    suite = "suite"


ViewMode = Literal["prompt", "skip", "every", "pipe"]
SaveMode = Literal["prompt", "skip", "every"]

OutputModes = tuple[ViewMode, SaveMode]
