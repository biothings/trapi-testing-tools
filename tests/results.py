from typing import override

import httpx

from tests import trapi
from tests.base_test import Test, TestResult


class ResultCount(Test):
    """has results."""

    @override
    @staticmethod
    def test(response: httpx.Response) -> TestResult:
        model = trapi.parse_or_fail(response)
        if isinstance(model, TestResult):
            return model
        n_results = len(model.message.results or [])

        return TestResult(n_results > 0, f"{n_results} results")


class NoResults(Test):
    """has no results."""

    @override
    @staticmethod
    def test(response: httpx.Response) -> TestResult:
        model = trapi.parse_or_fail(response)
        if isinstance(model, TestResult):
            return model
        n_results = len(model.message.results or [])

        return TestResult(n_results == 0, f"{n_results} results")
