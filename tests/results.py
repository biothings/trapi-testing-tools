from typing import override

import httpx

from tests import trapi
from tests.base_test import TestResult
from tests.params import Comparison, CountTest, count_result


class ResultCount(CountTest):
    """has results."""

    subject = "results"

    @override
    @staticmethod
    def test(
        response: httpx.Response, *, expected: int = 0, comparison: Comparison = "gt"
    ) -> TestResult:
        model = trapi.parse_or_fail(response)
        if isinstance(model, TestResult):
            return model
        count = len(model.message.results or [])
        return count_result(ResultCount.subject, count, expected, comparison)


NoResults = ResultCount.expect(0, "eq")
"""has no results (equivalent to ``ResultCount.expect(0)``)."""
