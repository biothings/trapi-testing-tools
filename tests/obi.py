"""Test for OBI (Ontology-Based Inference) behavior.

A lookup on a general term should also be answered via its subclasses, attributed to the
parent as a *construct edge* (`knowledge_level: logical_entailment`, `infores:obie`)
justified by a support graph = {the base edge on the descendant, the `subclass_of` edge}.
"""

from typing import Any, override

import httpx

from tests import trapi
from tests.base_test import Test, TestResult


def _knowledge_level(edge: Any) -> str | None:
    """An edge's knowledge_level across TRAPI versions (top-level in 2.0, attributes in 1.6)."""
    top_level = getattr(edge, "knowledge_level", None)
    if top_level is not None:
        return top_level
    for attribute in edge.attributes or []:
        if attribute.attribute_type_id == "biolink:knowledge_level":
            return attribute.value
    return None


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
            if _knowledge_level(edge) == "logical_entailment"
            and (edge.support_graphs or [])
        ]
        subclass = [
            edge_id
            for edge_id, edge in edges.items()
            if edge.predicate == "biolink:subclass_of"
        ]

        problems: list[str] = []
        if not construct:
            problems.append("no logical_entailment construct edge with a support graph")
        if not subclass:
            problems.append("no biolink:subclass_of edge")
        return TestResult(len(problems) == 0, problems or None)
