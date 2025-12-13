from typing import override

import httpx

from tests.base_test import Test, TestResult


class NodeCount(Test):
    """kg has nodes."""

    @override
    @staticmethod
    def test(response: httpx.Response) -> TestResult:
        body = response.json()
        node_count = len(body["message"]["knowledge_graph"]["nodes"].keys())
        return TestResult(node_count > 0, f"{node_count} nodes")


class EdgeCount(Test):
    """kg has edges."""

    @override
    @staticmethod
    def test(response: httpx.Response) -> TestResult:
        body = response.json()
        edge_count = len(body["message"]["knowledge_graph"]["edges"].keys())
        return TestResult(edge_count > 0, f"{edge_count} edges")


class SourceRecordURLs(Test):
    """has source_record_urls."""

    @override
    @staticmethod
    def test(response: httpx.Response) -> TestResult:
        body = response.json()

        has_source_record_urls = next(
            (
                edge
                for edge in body["message"]["knowledge_graph"]["edges"].values()
                if len(
                    [
                        source
                        for source in edge["sources"]
                        if source.get("source_record_urls", None) is not None
                    ]
                )
                > 0
            ),
            False,
        )
        return TestResult(
            has_source_record_urls > 0,
            "No edge has source_record_urls" if not has_source_record_urls else None,
        )


class HasKLAT(Test):
    """all edges have kl/at."""

    @override
    @staticmethod
    def test(response: httpx.Response) -> TestResult:
        body = response.json()

        missing = list[str]()
        for edge_id, edge in body["message"]["knowledge_graph"]["edges"].items():
            if (
                not len(
                    [
                        attr
                        for attr in edge["attributes"]
                        if attr["attribute_type_id"]
                        in ["biolink:knowledge_level", "biolink:agent_type"]
                    ]
                )
                >= 2  # noqa: PLR2004
            ):
                missing.append(edge_id)
        return TestResult(len(missing) == 0, missing if len(missing) == 0 else None)
