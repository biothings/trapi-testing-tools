from typing import override

import httpx

from tests.base_test import Test, TestResult
from tests.params import bind


class Status(Test):
    """status code 200."""

    @override
    @staticmethod
    def test(
        response: httpx.Response, *, codes: tuple[int, ...] = (200,)
    ) -> TestResult:
        passed = response.status_code in codes
        return TestResult(
            passed, None if passed else f"status is {response.status_code}"
        )

    @classmethod
    def expect(cls, *codes: int) -> type[Test]:
        """Build a variant passing when the status code is one of ``codes``.

        e.g. ``http.Status.expect(404)`` or ``http.Status.expect(200, 202)``.
        """
        listing = ", ".join(str(code) for code in codes)
        return bind(cls, name=f"status code ∈ ({listing})", codes=codes)
