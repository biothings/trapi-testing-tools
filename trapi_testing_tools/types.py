from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING, Any, Literal

from tests.base_test import Test

if TYPE_CHECKING:
    # translator_tom (TOM) is only referenced for typing; it is imported lazily at
    # runtime (in parse_query) so TOM-less, raw-dict query authoring never loads it.
    from translator_tom import TOMBase


class TestType(StrEnum):
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
    body: "dict[str, Any] | list[Any] | TOMBase | None" = None
    tests: list[type[Test]] | None = None
    trapi_version: Literal["1.6", "2.0"] = "1.6"
    """TRAPI version the response is parsed/validated against (see `trapi_models`)."""
