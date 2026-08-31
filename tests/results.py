from typing import override

import httpx

from tests import trapi
from tests.base_test import Test, TestResult
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


class ResultsBindQueryNodes(Test):
    """all results bind the query's nodes."""

    @override
    @staticmethod
    def test(response: httpx.Response) -> TestResult:
        model = trapi.parse_or_fail(response)
        if isinstance(model, TestResult):
            return model

        query_graph = model.message.query_graph
        if query_graph is None:
            return TestResult(True, "no query_graph")
        results = model.message.results_list

        # A qnode is required in every result if it's pinned (has ids) or ever bound.
        pinned = {qid for qid, qnode in query_graph.nodes.items() if qnode.ids}
        ever_bound = set().union(*(result.node_bindings.keys() for result in results))
        required = pinned | ever_bound

        missing = [
            f"result {i}: missing {', '.join(sorted(required - result.node_bindings.keys()))}"
            for i, result in enumerate(results)
            if not required <= result.node_bindings.keys()
        ]
        return TestResult(len(missing) == 0, missing or None)


class ResultsBindQueryEdges(Test):
    """all analyses bind the query's edges."""

    @override
    @staticmethod
    def test(response: httpx.Response) -> TestResult:
        model = trapi.parse_or_fail(response)
        if isinstance(model, TestResult):
            return model

        query_graph = model.message.query_graph
        if query_graph is None:
            return TestResult(True, "no query_graph")

        # pathfinder iff the graph has `paths` (1.6 PathfinderQueryGraph or 2.0 unified)
        paths = getattr(query_graph, "paths", None)
        pathfinder = bool(paths)
        declared = (paths if pathfinder else query_graph.edges).keys()
        kind = "path" if pathfinder else "edge"
        binding_attr = "path_bindings" if pathfinder else "edge_bindings"

        def bound(analysis: object) -> set[str]:
            bindings = getattr(analysis, binding_attr, None)
            return set(bindings.keys()) if bindings else set()

        # A qedge/qpath is required in every analysis iff some analysis binds it.
        analyses = [
            (i, j, analysis)
            for i, result in enumerate(model.message.results_list)
            for j, analysis in enumerate(result.analyses)
        ]
        ever_bound = set().union(*(bound(analysis) for _, _, analysis in analyses))
        required = set(declared) & ever_bound

        missing = [
            f"result {i} analysis {j}: missing {kind} binding for "
            f"{', '.join(sorted(required - bound(analysis)))}"
            for i, j, analysis in analyses
            if not required <= bound(analysis)
        ]
        return TestResult(len(missing) == 0, missing or None)
