from dataclasses import dataclass, field
from typing import override

import httpx
from translator_tom import Analysis, Message
from translator_tom.models.shared import CURIE, AuxGraphID, EdgeID

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


@dataclass
class _Reachability:
    """What a walk of a message's results reaches in the knowledge graph.

    An item is "reachable" if a result binds it directly, or if a support graph
    (referenced by a result's analysis, a pathfinder path binding, or, transitively,
    by a reachable edge) contains it. This mirrors the reference implementation in
    `translator_tom`'s `KnowledgeGraph.prune`, but collects dangling references
    instead of raising when a reference points outside the message.
    """

    nodes: set[CURIE] = field(default_factory=set)
    """kg.nodes keys that are reachable from the results."""

    edges: set[EdgeID] = field(default_factory=set)
    """kg.edges keys that are reachable from the results."""

    missing_nodes: set[CURIE] = field(default_factory=set)
    """Node references (bindings or edge nodes) absent from kg.nodes."""

    missing_edges: set[EdgeID] = field(default_factory=set)
    """Edge references (bindings or support-graph members) absent from kg.edges."""

    missing_aux_graphs: set[AuxGraphID] = field(default_factory=set)
    """Support/path-graph references absent from message.auxiliary_graphs."""


class _ReachabilityWalker:
    """Walks a message's results into its knowledge graph.

    Starts from result node bindings, edge bindings, analysis support
    graphs, pathfinder path bindings. Follows the support graphs
    of every reachable edge. References to nodes, edges, or auxiliary graphs not
    present in the message are recorded as missing rather than followed.
    """

    def __init__(self, message: Message) -> None:
        kg = message.knowledge_graph
        self._message = message
        self._nodes = kg.nodes if kg else {}
        self._edges = kg.edges if kg else {}
        self._aux_graphs = message.auxiliary_graphs_dict
        self._queue: list[EdgeID] = []
        self.reach = _Reachability()

    def _bind_node(self, node_id: CURIE) -> None:
        target = (
            self.reach.nodes if node_id in self._nodes else self.reach.missing_nodes
        )
        target.add(node_id)

    def _follow_aux_graph(self, aux_id: AuxGraphID) -> None:
        aux = self._aux_graphs.get(aux_id)
        if aux is None:
            self.reach.missing_aux_graphs.add(aux_id)
            return
        self._queue.extend(aux.edges)

    def _setup(self) -> None:
        """Queue directly-bound edges and record directly-bound nodes/aux graphs."""
        for result in self._message.results_list:
            for binding_set in result.node_bindings.values():
                for binding in binding_set:
                    self._bind_node(binding.id)
            for analysis in result.analyses:
                for aux_id in analysis.support_graphs_list:
                    self._follow_aux_graph(aux_id)
                if isinstance(analysis, Analysis):
                    for binding_set in analysis.edge_bindings.values():
                        self._queue.extend(binding.id for binding in binding_set)
                else:
                    for binding_set in analysis.path_bindings.values():
                        for binding in binding_set:
                            self._follow_aux_graph(binding.id)

    def _check(self) -> None:
        """Follow queued edges, binding nodes and support graphs."""
        checked: set[EdgeID] = set()  # Catch cycles
        while self._queue:
            edge_id = self._queue.pop()
            if edge_id in checked:
                continue
            checked.add(edge_id)

            edge = self._edges.get(edge_id)
            if edge is None:
                self.reach.missing_edges.add(edge_id)
                continue

            self.reach.edges.add(edge_id)
            self._bind_node(edge.subject)
            self._bind_node(edge.object)
            for aux_id in edge.support_graphs:
                self._follow_aux_graph(aux_id)

    def walk(self) -> _Reachability:
        """Get direct bindings and follow them out."""
        self._setup()
        self._check()
        return self.reach


def _walk_reachable(message: Message) -> _Reachability:
    """Walk a message's results into its knowledge graph (see `_ReachabilityWalker`)."""
    return _ReachabilityWalker(message).walk()


class AllKGItemsBound(Test):
    """all nodes/edges bound."""

    @override
    @staticmethod
    def test(response: httpx.Response) -> TestResult:
        model = trapi.parse_or_fail(response)
        if isinstance(model, TestResult):
            return model

        kg = model.message.knowledge_graph
        if kg is None:
            return TestResult(True, "no knowledge_graph")

        reach = _walk_reachable(model.message)
        unbound = [
            f"unbound node: {node_id}"
            for node_id in sorted(kg.nodes.keys() - reach.nodes)
        ] + [
            f"unbound edge: {edge_id}"
            for edge_id in sorted(kg.edges.keys() - reach.edges)
        ]
        return TestResult(len(unbound) == 0, unbound or None)


class BindingsResolveToKG(Test):
    """kg has all bound items."""

    @override
    @staticmethod
    def test(response: httpx.Response) -> TestResult:
        model = trapi.parse_or_fail(response)
        if isinstance(model, TestResult):
            return model

        reach = _walk_reachable(model.message)
        dangling = (
            [f"node not in kg: {node_id}" for node_id in sorted(reach.missing_nodes)]
            + [f"edge not in kg: {edge_id}" for edge_id in sorted(reach.missing_edges)]
            + [
                f"support graph not in auxiliary_graphs: {aux_id}"
                for aux_id in sorted(reach.missing_aux_graphs)
            ]
        )
        return TestResult(len(dangling) == 0, dangling or None)
