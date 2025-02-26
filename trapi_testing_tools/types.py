from enum import Enum


class LogLevel(Enum):
    ERROR = "ERROR"
    WARNING = "WARNING"
    INFO = "INFO"
    DEBUG = "DEBUG"


class TestType(Enum):
    asset = "asset"
    case = "case"
    suite = "suite"
