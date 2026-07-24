from typing import override

import httpx

from tests import trapi
from tests.base_test import Test, TestResult


class NodeCount(Test):
    """metakg has nodes."""

    @override
    @staticmethod
    def test(response: httpx.Response) -> TestResult:
        model = trapi.parse_metakg_or_fail(response)
        if isinstance(model, TestResult):
            return model
        node_count = len(model.nodes)
        return TestResult(node_count > 0, f"{node_count} nodes")


class EdgeCount(Test):
    """metakg has edges."""

    @override
    @staticmethod
    def test(response: httpx.Response) -> TestResult:
        model = trapi.parse_metakg_or_fail(response)
        if isinstance(model, TestResult):
            return model
        edge_count = len(model.edges)
        return TestResult(edge_count > 0, f"{edge_count} edges")
