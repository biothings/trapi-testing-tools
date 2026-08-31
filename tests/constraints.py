"""TRAPI 2.0 behavioral tests (constraint honoring, parameter echo, COLLATE) — 2.0-only.

Constraint checks are literal membership checks (no Biolink hierarchy expansion), so match
the exact values a component is expected to return.
"""

from collections import Counter
from typing import Any, override

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


class EdgesSatisfyQualifiers(Test):
    """kg edges satisfy the qualifiers constraint."""

    @override
    @staticmethod
    def test(
        response: httpx.Response,
        *,
        sets: tuple[tuple[tuple[str, str], ...], ...] = (),
    ) -> TestResult:
        model = trapi.parse_or_fail(response)
        if isinstance(model, TestResult):
            return model

        # A constraint's qualifier-sets are OR'd; the pairs within a set are AND'd (literal match).
        required_sets = [dict(pairs) for pairs in sets]
        violations: list[str] = []
        for edge_id, edge in _kg_edges(model).items():
            edge_quals = {
                qual.qualifier_type_id: qual.qualifier_value
                for qual in (edge.qualifiers or [])
            }
            satisfied = any(
                all(edge_quals.get(tid) == value for tid, value in required.items())
                for required in required_sets
            )
            if not satisfied:
                violations.append(f"{edge_id}: qualifiers={edge_quals}")
        return TestResult(len(violations) == 0, violations or None)

    @classmethod
    def expect(cls, *sets: dict[str, str]) -> type[Test]:
        """A variant asserting every KG edge satisfies ≥1 qualifier-set (OR of AND-ed pairs)."""
        frozen = tuple(tuple(one_set.items()) for one_set in sets)
        listing = " OR ".join(
            "{" + ", ".join(f"{k}={v}" for k, v in one_set.items()) + "}"
            for one_set in sets
        )
        return bind(cls, name=f"edges satisfy qualifiers {listing}", sets=frozen)


class ParametersEchoed(Test):
    """response echoes the query parameters."""

    @override
    @staticmethod
    def test(
        response: httpx.Response, *, expected: tuple[tuple[str, Any], ...] = ()
    ) -> TestResult:
        model = trapi.parse_or_fail(response)
        if isinstance(model, TestResult):
            return model

        params = getattr(model, "parameters", None)
        echoed = params.to_dict() if params is not None else {}
        if not expected:
            return TestResult(
                bool(echoed), None if echoed else "response has no parameters"
            )

        # Spec: the server MUST echo the parameters it received, so each sent pair must reappear.
        missing = [
            f"{key}={value!r} (got {echoed.get(key, '<absent>')!r})"
            for key, value in expected
            if echoed.get(key) != value
        ]
        return TestResult(len(missing) == 0, missing or None)

    @classmethod
    def expect(cls, **expected: Any) -> type[Test]:
        """A variant asserting the response echoes each given parameter key/value."""
        pairs = tuple(expected.items())
        listing = ", ".join(f"{k}={v!r}" for k, v in pairs)
        return bind(cls, name=f"parameters echo {{{listing}}}", expected=pairs)


class CollatedResultsUnique(Test):
    """collate: no two results collapse onto the collated qnode.

    Under COLLATE, matching ``qnode`` nodes fold into one result, so two results may not be
    identical once ``qnode`` and its incident edges are set aside — what distinguishes results
    is the rest of the graph: the other nodes *and* the edges connecting them.
    """

    @override
    @staticmethod
    def test(response: httpx.Response, *, qnode: str = "") -> TestResult:
        model = trapi.parse_or_fail(response)
        if isinstance(model, TestResult):
            return model

        query_graph = model.message.query_graph
        qedges = query_graph.edges if query_graph and query_graph.edges else {}
        incident = {
            qeid for qeid, qe in qedges.items() if qnode in (qe.subject, qe.object)
        }

        def collapse_key(result: Any) -> tuple[frozenset[Any], frozenset[Any]]:
            """A result's identity with the collated qnode and its incident edges removed."""
            nodes = frozenset(
                (qid, frozenset(binding_ids(binding)))
                for qid, binding in result.node_bindings.items()
                if qid != qnode
            )
            edges = frozenset(
                (qeid, frozenset(binding_ids(binding)))
                for analysis in (result.analyses or [])
                for qeid, binding in (analysis.edge_bindings or {}).items()
                if qedges and qeid not in incident
            )
            return nodes, edges

        keys = [collapse_key(result) for result in (model.message.results or [])]
        collided = sum(count for count in Counter(keys).values() if count > 1)
        return TestResult(
            collided == 0,
            None
            if collided == 0
            else f"{collided} results collapse on {qnode!r} (identical off the collated node+edges)",
        )

    @classmethod
    def expect(cls, qnode: str) -> type[Test]:
        """A variant asserting no two results collapse onto the collated ``qnode``."""
        return bind(cls, name=f"collate: no results collapse on {qnode}", qnode=qnode)
