"""Version dispatch for the TRAPI object model (TOM).

The TRAPI version is a per-query dimension: a query file's `trapi_version` rides on its
`Query`, the runner binds `current_trapi_version` around its tests, and TOM-parsing code
picks the matching model namespace via `models()`.
"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from typing import TYPE_CHECKING, Literal

import translator_tom.v1_6 as _v1_6
import translator_tom.v2_0 as _v2_0
from translator_tom.v1_6.validation import semantic_validate as _semantic_1_6
from translator_tom.v2_0.validation import semantic_validate as _semantic_2_0

if TYPE_CHECKING:
    from collections.abc import Iterator
    from types import ModuleType

TrapiVersion = Literal["1.6", "2.0"]
"""A supported TRAPI major version."""

DEFAULT_TRAPI_VERSION: TrapiVersion = "1.6"
"""The version assumed when a query file declares no `trapi_version`."""

_NAMESPACES: dict[TrapiVersion, ModuleType] = {"1.6": _v1_6, "2.0": _v2_0}
_SEMANTIC_VALIDATORS = {"1.6": _semantic_1_6, "2.0": _semantic_2_0}

SUPPORTED_VERSIONS: tuple[TrapiVersion, ...] = tuple(_NAMESPACES)
"""The TRAPI major versions TOM can parse and diff."""

current_trapi_version: ContextVar[TrapiVersion] = ContextVar(
    "current_trapi_version", default=DEFAULT_TRAPI_VERSION
)
"""The TRAPI version in effect for the query whose tests are currently running."""


def resolve(version: TrapiVersion | None = None) -> TrapiVersion:
    """The explicit `version`, else the active context version."""
    return version or current_trapi_version.get()


def models(version: TrapiVersion | None = None) -> ModuleType:
    """The TOM model namespace (`translator_tom.v1_6` / `.v2_0`) for `version`."""
    return _NAMESPACES[resolve(version)]


def detect_version(schema_version: str | None) -> TrapiVersion | None:
    """The supported TRAPI version a `schema_version` string denotes (e.g. `1.6.0` → `1.6`), if any."""
    if not schema_version:
        return None
    major_minor = ".".join(schema_version.split(".")[:2])
    return next((v for v in SUPPORTED_VERSIONS if v == major_minor), None)


def semantic_validate(model: object, version: TrapiVersion | None = None) -> object:
    """Run the version-appropriate `semantic_validate` on a parsed model."""
    return _SEMANTIC_VALIDATORS[resolve(version)](model)


@contextmanager
def use_version(version: TrapiVersion) -> Iterator[None]:
    """Bind `current_trapi_version` for the duration of the block."""
    token = current_trapi_version.set(version)
    try:
        yield
    finally:
        current_trapi_version.reset(token)
