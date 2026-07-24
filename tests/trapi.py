"""TOM-aware helpers for tests, backed by translator_tom.

Responses are parsed into TOM models at most once each (memoized per response
object).
"""

from __future__ import annotations

from typing import override
from weakref import WeakKeyDictionary

import httpx
from translator_tom import MetaKnowledgeGraph, Response
from translator_tom.validation import semantic_validate

from tests.base_test import Test, TestResult


class TrapiParseError(Exception):
    """Raised when a response body cannot be parsed as the expected TRAPI model."""


# Cache parsed model or parse error per response to avoid slow re-parsing.
_TRAPI_CACHE: WeakKeyDictionary[httpx.Response, Response | TrapiParseError] = (
    WeakKeyDictionary()
)
_METAKG_CACHE: WeakKeyDictionary[
    httpx.Response, MetaKnowledgeGraph | TrapiParseError
] = WeakKeyDictionary()


def as_trapi(response: httpx.Response) -> Response:
    """Parse a response into a TOM `Response`, memoized per response.

    Raises:
        TrapiParseError: if the body is not valid TRAPI (also cached and re-raised).
    """
    cached = _TRAPI_CACHE.get(response)
    if cached is not None:
        if isinstance(cached, TrapiParseError):
            raise cached
        return cached

    try:
        parsed = Response.from_json(response.content)
    except Exception as error:
        parse_error = TrapiParseError(f"response is not valid TRAPI: {error}")
        _TRAPI_CACHE[response] = parse_error
        raise parse_error from error

    _TRAPI_CACHE[response] = parsed
    return parsed


def as_metakg(response: httpx.Response) -> MetaKnowledgeGraph:
    """Parse a response into a TOM `MetaKnowledgeGraph`, memoized per response.

    Raises:
        TrapiParseError: if the body is not a valid meta_knowledge_graph.
    """
    cached = _METAKG_CACHE.get(response)
    if cached is not None:
        if isinstance(cached, TrapiParseError):
            raise cached
        return cached

    try:
        parsed = MetaKnowledgeGraph.from_json(response.content)
    except Exception as error:
        parse_error = TrapiParseError(
            f"response is not a valid meta_knowledge_graph: {error}"
        )
        _METAKG_CACHE[response] = parse_error
        raise parse_error from error

    _METAKG_CACHE[response] = parsed
    return parsed


def parse_or_fail(response: httpx.Response) -> Response | TestResult:
    """Parse a TRAPI `Response` or produce a failed `TestResult`.

    Lets tests type-narrow to model, or fail early due to the parse fail.
    """
    try:
        return as_trapi(response)
    except TrapiParseError as error:
        return TestResult(False, str(error))


def parse_metakg_or_fail(
    response: httpx.Response,
) -> MetaKnowledgeGraph | TestResult:
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
