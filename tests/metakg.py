from typing import override

import httpx

from tests import trapi
from tests.base_test import TestResult
from tests.params import Comparison, CountTest, count_result


class NodeCount(CountTest):
    """metakg has nodes."""

    subject = "metakg nodes"

    @override
    @staticmethod
    def test(
        response: httpx.Response, *, expected: int = 0, comparison: Comparison = "gt"
    ) -> TestResult:
        model = trapi.parse_metakg_or_fail(response)
        if isinstance(model, TestResult):
            return model
        return count_result(NodeCount.subject, len(model.nodes), expected, comparison)


class EdgeCount(CountTest):
    """metakg has edges."""

    subject = "metakg edges"

    @override
    @staticmethod
    def test(
        response: httpx.Response, *, expected: int = 0, comparison: Comparison = "gt"
    ) -> TestResult:
        model = trapi.parse_metakg_or_fail(response)
        if isinstance(model, TestResult):
            return model
        return count_result(EdgeCount.subject, len(model.edges), expected, comparison)
