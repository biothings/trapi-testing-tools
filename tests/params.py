"""Shared parametrization helpers for tests.

Count-based tests (nodes, edges, results) subclass `CountTest`, set `subject`, and
implement a keyword-parametrized `test` that returns `count_result(...)`. Used bare a
count test asserts "there are some" (``> 0``); `CountTest.expect(...)` builds a variant
with a different threshold and operator, e.g. ``ResultCount.expect(50, "gte")``. `bind`
is the generic builder any parametrized family uses to turn bound keyword arguments into
a plain, list-usable `type[Test]`.
"""

import operator
from collections.abc import Callable
from typing import ClassVar, Literal, cast

import httpx

from tests.base_test import Test, TestResult

Comparison = Literal["lt", "lte", "eq", "ne", "gte", "gt"]
"""A comparison operator for count-based tests."""

_COMPARATORS: dict[Comparison, Callable[[int, int], bool]] = {
    "lt": operator.lt,
    "lte": operator.le,
    "eq": operator.eq,
    "ne": operator.ne,
    "gte": operator.ge,
    "gt": operator.gt,
}

_SYMBOLS: dict[Comparison, str] = {
    "lt": "<",
    "lte": "≤",
    "eq": "=",
    "ne": "≠",
    "gte": "≥",
    "gt": ">",
}


def compare(actual: int, expected: int, comparison: Comparison) -> bool:
    """Whether ``actual`` satisfies ``comparison`` against ``expected``."""
    return _COMPARATORS[comparison](actual, expected)


def comparison_symbol(comparison: Comparison) -> str:
    """The math symbol for a comparison operator, for labels and reports."""
    return _SYMBOLS[comparison]


def count_result(
    subject: str, count: int, expected: int, comparison: Comparison
) -> TestResult:
    """A pass/fail `TestResult` comparing ``count`` against ``expected``.

    ``subject`` is the report noun (e.g. ``"kg nodes"``); the info shows the actual
    count, and the expectation too when the comparison fails.
    """
    passed = compare(count, expected, comparison)
    info = f"{count} {subject}"
    if not passed:
        info += f" (expected {comparison_symbol(comparison)} {expected})"
    return TestResult(passed, info)


def bind(cls: type[Test], /, name: str | None = None, **params: object) -> type[Test]:
    """A `Test` variant whose `test` runs ``cls.test`` with ``params`` pre-applied.

    ``name``, when given, becomes the variant's docstring — i.e. its display label.
    This is the single mechanism parametrized test families use to turn bound
    keyword arguments into a plain, list-usable `type[Test]` (see `CountTest.expect`).
    The base `Test.test` signature does not carry a subclass's extra keyword params,
    so the delegation is cast to a permissive callable.
    """
    parametrized = cast(Callable[..., TestResult], cls.test)

    def test(response: httpx.Response) -> TestResult:
        return parametrized(response, **params)

    return type(
        cls.__name__,
        (Test,),
        {"test": staticmethod(test), "__doc__": name or cls.__doc__},
    )


class CountTest(Test):
    """Base for count-based tests: assert a count satisfies a comparison.

    Subclasses set `subject` (the report noun, e.g. ``"kg nodes"``) and implement a
    keyword-parametrized ``test(response, *, expected=0, comparison="gt")`` that returns
    ``count_result(cls.subject, <count>, expected, comparison)``. Used bare the defaults
    assert ``> 0`` (i.e. "there are some"); `expect` builds a variant with a different
    threshold/operator, e.g. ``ResultCount.expect(50, "gte")``.
    """

    subject: ClassVar[str] = "items"
    """The noun for the counted thing, used in pass/fail reports."""

    @classmethod
    def expect(cls, expected: int, comparison: Comparison = "eq") -> type[Test]:
        """Build a variant asserting the count ``comparison`` ``expected``.

        e.g. ``kg.EdgeCount.expect(50, "gte")`` requires at least 50 edges, and
        ``results.ResultCount.expect(0)`` requires exactly none.
        """
        return bind(
            cls,
            name=f"{cls.subject} {comparison_symbol(comparison)} {expected}",
            expected=expected,
            comparison=comparison,
        )
