"""TRAPI 2.0 behavioral tests (constraint honoring, parameter echo, COLLATE) — 2.0-only.

Constraint checks are literal membership checks (no Biolink hierarchy expansion), so match
the exact values a component is expected to return.
"""

from typing import override

import httpx

from tests import trapi
from tests.base_test import Test, TestResult
from tests.kg import binding_ids
from tests.params import bind


def _kg_edges(model: object) -> dict[str, object]:
    """The knowledge-graph edges of a parsed response (empty when absent)."""
    kg = model.message.knowledge_graph
    return kg.edges if kg else {}


class EdgesSatisfyKLAT(Test):
    """kg edges satisfy the kl/at constraint."""

    @override
    @staticmethod
    def test(
        response: httpx.Response,
        *,
        field: str = "knowledge_level",
        behavior: str = "ALLOW",
        values: tuple[str, ...] = (),
    ) -> TestResult:
        model = trapi.parse_or_fail(response)
        if isinstance(model, TestResult):
            return model

        wanted = set(values)
        violations: list[str] = []
        for edge_id, edge in _kg_edges(model).items():
            actual = getattr(edge, field, None)
            hit = actual in wanted
            satisfied = hit if behavior == "ALLOW" else not hit
            if not satisfied:
                violations.append(f"{edge_id}: {field}={actual!r}")
        return TestResult(len(violations) == 0, violations or None)

    @classmethod
    def expect(cls, field: str, behavior: str, *values: str) -> type[Test]:
        """A variant asserting every KG edge's KL/AT ``field`` satisfies the constraint."""
        return bind(
            cls,
            name=f"edges {behavior} {field} ∈ {list(values)}",
            field=field,
            behavior=behavior,
            values=values,
        )


class EdgesSatisfySources(Test):
    """kg edges satisfy the sources constraint."""

    @override
    @staticmethod
    def test(
        response: httpx.Response,
        *,
        behavior: str = "ALLOW",
        values: tuple[str, ...] = (),
        primary_only: bool = False,
    ) -> TestResult:
        model = trapi.parse_or_fail(response)
        if isinstance(model, TestResult):
            return model

        wanted = set(values)
        violations: list[str] = []
        for edge_id, edge in _kg_edges(model).items():
            infores = {
                source.resource_id
                for source in edge.sources
                if not primary_only
                or source.resource_role == "primary_knowledge_source"
            }
            hit = bool(infores & wanted)
            satisfied = hit if behavior == "ALLOW" else not hit
            if not satisfied:
                violations.append(f"{edge_id}: sources={sorted(infores)}")
        return TestResult(len(violations) == 0, violations or None)

    @classmethod
    def expect(
        cls, behavior: str, *values: str, primary_only: bool = False
    ) -> type[Test]:
        """A variant asserting every KG edge's ``sources`` satisfy the constraint."""
        scope = " (primary only)" if primary_only else ""
        return bind(
            cls,
            name=f"edges {behavior} sources ∈ {list(values)}{scope}",
            behavior=behavior,
            values=values,
            primary_only=primary_only,
        )


class ParametersEchoed(Test):
    """response echoes query parameters."""

    @override
    @staticmethod
    def test(response: httpx.Response) -> TestResult:
        model = trapi.parse_or_fail(response)
        if isinstance(model, TestResult):
            return model
        params = getattr(model, "parameters", None)
        passed = bool(params)
        return TestResult(passed, None if passed else "response has no parameters")


class CollatedIntoSingleResult(Test):
    """collate yields one result with a multi-id node binding."""

    @override
    @staticmethod
    def test(
        response: httpx.Response, *, qnode: str = "", min_ids: int = 2
    ) -> TestResult:
        model = trapi.parse_or_fail(response)
        if isinstance(model, TestResult):
            return model

        results = model.message.results or []
        if len(results) != 1:
            return TestResult(False, f"expected 1 collated result, got {len(results)}")

        bindings = results[0].node_bindings.get(qnode)
        if bindings is None:
            return TestResult(False, f"no node binding for qnode {qnode!r}")

        ids = list(binding_ids(bindings))
        passed = len(ids) >= min_ids
        return TestResult(
            passed,
            None
            if passed
            else f"qnode {qnode!r} bound {len(ids)} id(s), want ≥ {min_ids}",
        )

    @classmethod
    def expect(cls, qnode: str, min_ids: int = 2) -> type[Test]:
        """A variant asserting ``qnode`` binds at least ``min_ids`` ids in one result."""
        return bind(
            cls,
            name=f"collate: {qnode} binds ≥ {min_ids} in 1 result",
            qnode=qnode,
            min_ids=min_ids,
        )
