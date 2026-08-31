from typing import override

import httpx

from tests import trapi
from tests.base_test import Test, TestResult
from tests.params import bind


class TrapiStatus(Test):
    """trapi status is Success."""

    @override
    @staticmethod
    def test(
        response: httpx.Response, *, statuses: tuple[str, ...] = ("Success",)
    ) -> TestResult:
        model = trapi.parse_or_fail(response)
        if isinstance(model, TestResult):
            return model
        actual = model.status
        passed = actual in statuses
        return TestResult(passed, None if passed else f"status is {actual!r}")

    @classmethod
    def expect(cls, *statuses: str) -> type[Test]:
        """Build a variant passing when the TRAPI ``status`` field is one of ``statuses``.

        e.g. ``TrapiStatus.expect("QueryNotTraversable", "UnsupportedConstraint")``.
        """
        listing = ", ".join(statuses)
        return bind(cls, name=f"trapi status ∈ ({listing})", statuses=statuses)
