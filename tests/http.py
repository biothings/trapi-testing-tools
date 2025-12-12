from typing import override

import httpx

from tests.base_test import Test, TestResult


def status(*status_code: int) -> type[Test]:
    """Generate a status test for the given status code set."""

    class StatusTest(Test):
        @override
        @staticmethod
        def test(response: httpx.Response) -> TestResult:
            passed = response.status_code in [*status_code]
            return TestResult(
                passed,
                info=f"status is {response.status_code}" if not passed else None,
            )

    StatusTest.__doc__ = (
        f"status code ∈ ({', '.join([str(code) for code in status_code])})."
    )

    return StatusTest
