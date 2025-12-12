from typing import override

import httpx

from tests.base_test import Test, TestResult


class ResultCount(Test):
    """has results."""

    @override
    @staticmethod
    def test(response: httpx.Response) -> TestResult:
        body = response.json()
        n_results = len(body["message"]["results"])

        return TestResult(n_results > 0, f"{n_results} results")


class NoResults(Test):
    """has no results."""

    @override
    @staticmethod
    def test(response: httpx.Response) -> TestResult:
        body = response.json()
        n_results = len(body["message"]["results"])

        return TestResult(n_results == 0, f"{n_results} results")
