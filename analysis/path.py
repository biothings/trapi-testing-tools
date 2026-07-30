from collections import Counter, defaultdict
from contextlib import redirect_stdout
from sys import stderr, stdin
from typing import Annotated

import typer
from InquirerPy.prompts.fuzzy import FuzzyPrompt
from translator_tom import Response
from translator_tom.models.knowledge_graph import KnowledgeGraph
from translator_tom.models.query_graph import PathfinderQueryGraph
from translator_tom.models.shared import CURIE, QNodeID

from analysis.base_analysis import AnalysisOutput, ParametrizedAnalysis

StartOption = Annotated[
    str | None,
    typer.Option("--start", "-s", help="Start node CURIE (KG node id)."),
]
EndOption = Annotated[
    str | None,
    typer.Option("--end", "-e", help="End node CURIE (KG node id)."),
]
_CTX = {"ignore_unknown_options": True, "allow_extra_args": True}


def _adjacency(kg: KnowledgeGraph) -> dict[CURIE, set[CURIE]]:
    """Directed subject->object adjacency, excluding support-graph-backed edges."""
    adjacency: dict[CURIE, set[CURIE]] = defaultdict(set)
    for edge in kg.edges.values():
        if edge.support_graphs:
            continue
        adjacency[edge.subject].add(edge.object)
    return adjacency


def _get_paths(kg: KnowledgeGraph, start: CURIE, end: CURIE) -> list[list[CURIE]]:
    """All simple directed paths from start to end through the (real) KG."""
    adjacency = _adjacency(kg)
    paths: list[list[CURIE]] = []
    stack: list[tuple[CURIE, list[CURIE]]] = [(start, [start])]
    while stack:
        node, path = stack.pop()
        if node == end:
            paths.append(path)
            continue
        stack.extend(
            (neighbor, [*path, neighbor])
            for neighbor in adjacency.get(node, ())
            if neighbor not in path
        )
    return paths


def _pinned_trace_nodes(response: Response) -> list[CURIE]:
    """Pinned query-graph trace nodes, in a principled order when possible."""
    qg = response.message.query_graph
    if qg is None:
        return []
    if isinstance(qg, PathfinderQueryGraph):
        qpath = next(iter(qg.paths.values()))
        ordered = [
            qg.nodes[qnode_id]
            for qnode_id in (qpath.subject, qpath.object)
            if qnode_id in qg.nodes
        ]
    else:
        ordered = list(qg.nodes.values())
    return [qnode.ids_list[0] for qnode in ordered if qnode.ids_list]


def _pinned_qnode_ids(response: Response) -> dict[CURIE, list[QNodeID]]:
    """Map each pinned CURIE to the qnode id(s) that pinned it in the query graph."""
    mapping: dict[CURIE, list[QNodeID]] = defaultdict(list)
    qg = response.message.query_graph
    if qg is not None:
        for qnode_id, qnode in qg.nodes.items():
            for curie in qnode.ids_list:
                mapping[curie].append(qnode_id)
    return mapping


def _candidates(response: Response, exclude: set[CURIE]) -> list[CURIE]:
    """Selectable trace nodes: qgraph-pinned CURIEs, or all KG nodes once exhausted.

    Restricts selection to CURIEs pinned in the query graph (minus `exclude`); only
    when that pool is empty (none pinned, or all already chosen) does it fall back
    to every KG node.
    """
    kg = response.message.knowledge_graph
    assert kg is not None  # guaranteed by _resolve_trace_nodes
    pinned = [curie for curie in _pinned_qnode_ids(response) if curie not in exclude]
    if pinned:
        return pinned
    return [curie for curie in kg.nodes if curie not in exclude]


def _prompt_curie(
    response: Response, which: str, candidates: list[CURIE]
) -> str | None:
    """Fuzzy-pick a CURIE from `candidates`.

    Pinned nodes are annotated with their qnode id(s); labels show the node name
    (when known) for searching.
    """
    kg = response.message.knowledge_graph
    assert kg is not None  # guaranteed by _resolve_trace_nodes
    pinned = _pinned_qnode_ids(response)

    label_to_curie = dict[str, CURIE]()
    for curie in candidates:
        node = kg.nodes.get(curie)
        name = node.name if node and node.name else "?"
        if curie in pinned:
            qnodes = ", ".join(pinned[curie])
            label_to_curie[f"[{qnodes}] {curie}  ·  {name}"] = curie
        else:
            label_to_curie[f"{curie}  ·  {name}"] = curie

    with redirect_stdout(stderr):
        selection: str = FuzzyPrompt(
            message=f"Select {which} node...",
            choices=list(label_to_curie),
            border=True,
            instruction="(Type to filter, Enter to confirm)",
            info=True,
        ).execute()
    return label_to_curie.get(selection)


def _resolve_trace_nodes(
    response: Response, start: str | None, end: str | None
) -> tuple[CURIE, CURIE] | str:
    """Resolve (start, end) CURIEs, or return an explanatory note string."""
    kg = response.message.knowledge_graph
    if kg is None or not kg.nodes:
        return "response has no knowledge_graph nodes to trace paths through"

    if not (start and end) and stdin.isatty():
        if not start:
            start = _prompt_curie(
                response, "start", _candidates(response, {end} if end else set())
            )
        if not end:
            end = _prompt_curie(
                response, "end", _candidates(response, {start} if start else set())
            )
    else:
        # Non-interactive: fall back to pinned query-graph trace nodes.
        pinned = _pinned_trace_nodes(response)
        start = start or (pinned[0] if pinned else None)
        end = end or (pinned[1] if len(pinned) > 1 else None)

    if not start or not end or start == end:
        return (
            "could not determine two distinct nodes; supply them after `--`, "
            "e.g. `-- --start <CURIE> --end <CURIE>`"
        )
    return start, end


_count_app = typer.Typer(add_completion=False)


@_count_app.command(context_settings=_CTX)
def _count(
    ctx: typer.Context, start: StartOption = None, end: EndOption = None
) -> AnalysisOutput:
    """Count directed paths between two nodes, bucketed by length."""
    response: Response = ctx.obj
    trace_nodes = _resolve_trace_nodes(response, start, end)
    if isinstance(trace_nodes, str):
        return {"note": trace_nodes}
    start_curie, end_curie = trace_nodes
    kg = response.message.knowledge_graph
    assert kg is not None  # guaranteed by _resolve_trace_nodes
    lengths = Counter(len(path) - 1 for path in _get_paths(kg, start_curie, end_curie))
    return {
        "start": start_curie,
        "end": end_curie,
        "paths_by_length": {str(length): lengths[length] for length in sorted(lengths)},
    }


_list_app = typer.Typer(add_completion=False)


@_list_app.command(context_settings=_CTX)
def _list(
    ctx: typer.Context, start: StartOption = None, end: EndOption = None
) -> AnalysisOutput:
    """List directed paths between two nodes."""
    response: Response = ctx.obj
    trace_nodes = _resolve_trace_nodes(response, start, end)
    if isinstance(trace_nodes, str):
        return {"note": trace_nodes}
    start_curie, end_curie = trace_nodes
    kg = response.message.knowledge_graph
    assert kg is not None  # guaranteed by _resolve_trace_nodes
    paths = sorted(_get_paths(kg, start_curie, end_curie), key=len)
    return {"start": start_curie, "end": end_curie, "paths": paths}


class PathCount(ParametrizedAnalysis):
    """count of directed paths by length."""

    app = _count_app


class PathList(ParametrizedAnalysis):
    """list of directed paths between two nodes."""

    app = _list_app
