from typing import override

import httpx

from tests.base_test import Test, TestResult


class NodeCount(Test):
    """metakg has nodes."""

    @override
    @staticmethod
    def test(response: httpx.Response) -> TestResult:
        node_count = len(response.json()["nodes"].keys())
        return TestResult(node_count > 0, f"{node_count} nodes")


class EdgeCount(Test):
    """metakg has edges."""

    @override
    @staticmethod
    def test(response: httpx.Response) -> TestResult:
        edge_count = len(response.json()["edges"])
        return TestResult(edge_count > 0, f"{edge_count} edges")
