"""Test for OBI (Ontology-Based Inference) behavior.

A lookup on a general term should also be answered via its subclasses, attributed to the
parent as a *construct edge* whose primary knowledge source is `infores:obie` (the marker),
justified by a support graph = {the base edge on the descendant, the `subclass_of` edge}.
"""

from typing import Any, override

import httpx

from tests import trapi
from tests.base_test import Test, TestResult


def _obie_primary(edge: Any) -> bool:
    """Whether infores:obie is the edge's primary knowledge source — the OBI marker."""
    return any(
        source.resource_id == "infores:obie"
        and source.resource_role == "primary_knowledge_source"
        for source in edge.sources
    )


class HasOBIConstruct(Test):
    """has OBI edge constructs."""

    @override
    @staticmethod
    def test(response: httpx.Response) -> TestResult:
        model = trapi.parse_or_fail(response)
        if isinstance(model, TestResult):
            return model

        kg = model.message.knowledge_graph
        edges = kg.edges if kg else {}
        construct = [
            edge_id
            for edge_id, edge in edges.items()
            if _obie_primary(edge) and (edge.support_graphs or [])
        ]
        subclass = [
            edge_id
            for edge_id, edge in edges.items()
            if edge.predicate == "biolink:subclass_of"
        ]

        problems: list[str] = []
        if not construct:
            problems.append("no infores:obie construct edge with a support graph")
        if not subclass:
            problems.append("no biolink:subclass_of edge")
        return TestResult(len(problems) == 0, problems or None)
