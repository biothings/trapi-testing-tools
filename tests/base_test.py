from abc import ABC, abstractmethod
from typing import NamedTuple

import httpx


class TestResult(NamedTuple):
    """A test result that states whether the test passed, and can pass along additional info."""

    passed: bool
    info: str | list[str] | None


class Test(ABC):
    """A static class for a single test with consistent I/O.

    Writing a docstring on implemented classes means the docstring will be used to when printing the test/result, minus the final period.
    """

    @staticmethod
    @abstractmethod
    def test(response: httpx.Response) -> TestResult:
        """A test that takes the httpx response and returns a pass/fail and optional info."""
