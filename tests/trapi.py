"""TOM-aware helpers for tests, backed by translator_tom.

Responses parse to TOM models once per (response, version), with the namespace + validator
resolved from the active `current_trapi_version`, so tests stay version-agnostic.
"""

from __future__ import annotations

from typing import Any, override
from weakref import WeakKeyDictionary

import httpx

from tests.base_test import Test, TestResult
from trapi_testing_tools.trapi_models import (
    current_trapi_version,
    models,
    semantic_validate,
)


class TrapiParseError(Exception):
    """Raised when a response body cannot be parsed as the expected TRAPI model."""


# Cache parsed model or parse error per (response, version) to avoid slow re-parsing.
_TRAPI_CACHE: WeakKeyDictionary[httpx.Response, dict[str, Any]] = WeakKeyDictionary()
_METAKG_CACHE: WeakKeyDictionary[httpx.Response, dict[str, Any]] = WeakKeyDictionary()


def as_trapi(response: httpx.Response) -> Any:
    """Parse a response into a TOM `Response` for the active version, memoized.

    Raises:
        TrapiParseError: if the body is not valid TRAPI (also cached and re-raised).
    """
    version = current_trapi_version.get()
    per_version = _TRAPI_CACHE.setdefault(response, {})
    cached = per_version.get(version)
    if cached is not None:
        if isinstance(cached, TrapiParseError):
            raise cached
        return cached

    try:
        parsed = models(version).Response.from_json(response.content)
    except Exception as error:
        parse_error = TrapiParseError(f"response is not valid TRAPI {version}: {error}")
        per_version[version] = parse_error
        raise parse_error from error

    per_version[version] = parsed
    return parsed


def as_metakg(response: httpx.Response) -> Any:
    """Parse a response into a TOM `MetaKnowledgeGraph` for the active version, memoized.

    Raises:
        TrapiParseError: if the body is not a valid meta_knowledge_graph.
    """
    version = current_trapi_version.get()
    per_version = _METAKG_CACHE.setdefault(response, {})
    cached = per_version.get(version)
    if cached is not None:
        if isinstance(cached, TrapiParseError):
            raise cached
        return cached

    try:
        parsed = models(version).MetaKnowledgeGraph.from_json(response.content)
    except Exception as error:
        parse_error = TrapiParseError(
            f"response is not a valid meta_knowledge_graph ({version}): {error}"
        )
        per_version[version] = parse_error
        raise parse_error from error

    per_version[version] = parsed
    return parsed


def parse_or_fail(response: httpx.Response) -> Any | TestResult:
    """Parse a TRAPI `Response` or produce a failed `TestResult`.

    Lets tests type-narrow to model, or fail early due to the parse fail.
    """
    try:
        return as_trapi(response)
    except TrapiParseError as error:
        return TestResult(False, str(error))


def parse_metakg_or_fail(
    response: httpx.Response,
) -> Any | TestResult:
    """Parse a `MetaKnowledgeGraph` or produce a failed `TestResult`."""
    try:
        return as_metakg(response)
    except TrapiParseError as error:
        return TestResult(False, str(error))


def _format_finding(item: object) -> str:
    """Render a semantic-validation warning/error as `location -> message`."""
    location = getattr(item, "location", None)
    message = getattr(item, "message", None) or str(item)
    return f"{location} -> {message}" if location else message


class Structural(Test):
    """response is valid TRAPI."""

    @override
    @staticmethod
    def test(response: httpx.Response) -> TestResult:
        result = parse_or_fail(response)
        if isinstance(result, TestResult):
            return result
        return TestResult(True, None)


class Semantic(Test):
    """response passes semantic validation."""

    @override
    @staticmethod
    def test(response: httpx.Response) -> TestResult:
        model = parse_or_fail(response)
        if isinstance(model, TestResult):
            return model

        warnings, errors = semantic_validate(model)

        if errors:
            report = [_format_finding(error) for error in errors]
            report += [f"(warning) {_format_finding(w)}" for w in warnings]
            return TestResult(False, report)

        info = [f"(warning) {_format_finding(w)}" for w in warnings] or None
        return TestResult(True, info)
