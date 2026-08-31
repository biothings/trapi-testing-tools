from typing import override

from translator_tom import EdgeID
from translator_tom.v2_0 import Response

from analysis.base_analysis import Analysis, AnalysisOutput


class SupportGraphHierarchy(Analysis):
    """support-graph nesting per result."""

    @override
    @staticmethod
    def analyze(response: Response) -> AnalysisOutput:
        message = response.message
        kg = message.knowledge_graph
        if kg is None:
            return {"max_depth": 0, "max_depth_result": None, "hierarchy": []}

        edges = kg.edges
        aux = message.auxiliary_graphs_dict

        max_depth = 1
        max_depth_result: int | None = None

        def build(edge_id: EdgeID, depth: int, path: frozenset[EdgeID]) -> object:
            """Recursively expand an edge into its support-graph hierarchy."""
            nonlocal max_depth
            max_depth = max(depth, max_depth)
            edge = edges.get(edge_id)
            if edge is None:
                return f"<missing edge: {edge_id}>"
            support_graphs = edge.support_graphs
            # Leaf: no support graphs, or a cycle back onto an ancestor edge.
            if not support_graphs or edge_id in path:
                return [edge.subject, str(edge.predicate), edge.object]
            nested: dict[str, object] = {}
            ancestors = path | {edge_id}
            for aux_id in support_graphs:
                aux_graph = aux.get(aux_id)
                if aux_graph is None:
                    nested[aux_id] = f"<missing support graph: {aux_id}>"
                    continue
                for sub_id in aux_graph.edges:
                    nested[sub_id] = build(sub_id, depth + 1, ancestors)
            return nested

        hierarchy: list[dict] = []
        for i, result in enumerate(message.results_list):
            result_hierarchy: dict[str, dict] = {}
            hierarchy.append(result_hierarchy)
            for analysis in result.analyses:
                # 2.0 unifies Analysis; edge_bindings may be absent on a path-only analysis.
                for qedge_id, bindings in (analysis.edge_bindings or {}).items():
                    bound = result_hierarchy.setdefault(qedge_id, {})
                    for edge_id in bindings.ids:
                        prev = max_depth
                        bound[edge_id] = build(edge_id, 1, frozenset())
                        if max_depth > prev:
                            max_depth_result = i

        return {
            "max_depth": max_depth,
            "max_depth_result": max_depth_result,
            "hierarchy": hierarchy,
        }
