from typing import override

import httpx

from tests import trapi
from tests.base_test import Test, TestResult


class NodeCount(Test):
    """kg has nodes."""

    @override
    @staticmethod
    def test(response: httpx.Response) -> TestResult:
        model = trapi.parse_or_fail(response)
        if isinstance(model, TestResult):
            return model
        kg = model.message.knowledge_graph
        node_count = len(kg.nodes) if kg else 0
        return TestResult(node_count > 0, f"{node_count} nodes")


class EdgeCount(Test):
    """kg has edges."""

    @override
    @staticmethod
    def test(response: httpx.Response) -> TestResult:
        model = trapi.parse_or_fail(response)
        if isinstance(model, TestResult):
            return model
        kg = model.message.knowledge_graph
        edge_count = len(kg.edges) if kg else 0
        return TestResult(edge_count > 0, f"{edge_count} edges")


class SourceRecordURLs(Test):
    """has source_record_urls."""

    @override
    @staticmethod
    def test(response: httpx.Response) -> TestResult:
        model = trapi.parse_or_fail(response)
        if isinstance(model, TestResult):
            return model

        kg = model.message.knowledge_graph
        edges = kg.edges if kg else {}
        has_source_record_urls = any(
            source.source_record_urls
            for edge in edges.values()
            for source in edge.sources
        )
        return TestResult(
            has_source_record_urls,
            None if has_source_record_urls else "No edge has source_record_urls",
        )


class HasKLAT(Test):
    """all edges have kl/at."""

    @override
    @staticmethod
    def test(response: httpx.Response) -> TestResult:
        model = trapi.parse_or_fail(response)
        if isinstance(model, TestResult):
            return model

        required = {"biolink:knowledge_level", "biolink:agent_type"}
        kg = model.message.knowledge_graph
        edges = kg.edges if kg else {}
        missing = [
            edge_id
            for edge_id, edge in edges.items()
            if not required.issubset(
                {attr.attribute_type_id for attr in (edge.attributes or [])}
            )
        ]
        return TestResult(len(missing) == 0, missing or None)
