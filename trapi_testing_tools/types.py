from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Literal

from tests.base_test import Test


class LogLevel(str, Enum):
    """Common TRAPI log levels."""

    ERROR = "ERROR"
    WARNING = "WARNING"
    INFO = "INFO"
    DEBUG = "DEBUG"


class TestType(str, Enum):
    """Type of test in the automated testing suite."""

    asset = "asset"
    case = "case"
    suite = "suite"


HTTPMethod = Literal["GET", "OPTIONS", "HEAD", "POST", "PUT", "PATCH", "DELETE"]
"""Supported HTTP methods."""


ViewMode = Literal["prompt", "skip", "every", "pipe"]
SaveMode = Literal["prompt", "skip", "every"]

OutputModes = tuple[ViewMode, SaveMode]


@dataclass(kw_only=True, frozen=True)
class Query:
    """A query to be run by the testing tools."""

    method: HTTPMethod = "GET"
    endpoint: str | None = None
    params: dict[str, Any] = field(default_factory=dict)
    headers: dict[str, str] = field(default_factory=dict)
    body: dict[str, Any] | list[Any] | None = None
    tests: list[type[Test]] | None = None
