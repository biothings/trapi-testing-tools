"""Convenience constructors for building TRAPI query bodies with translator_tom."""

from pathlib import Path
from typing import Any

from translator_tom import (
    Biolink,
    Message,
    PathfinderQueryGraph,
    QEdge,
    QNode,
    Qualifier,
    QualifierConstraint,
    Query,
    QueryGraph,
)


def _as_list(value: str | list[str] | None) -> list[str] | None:
    """Normalize a str-or-list argument to a list (or None if unset)."""
    if value is None:
        return None
    return [value] if isinstance(value, str) else list(value)


def _categories(spec: str | list[str] | None) -> list[str] | None:
    """Normalize category CURIE(s), accepting bare (`Gene`) or prefixed forms."""
    values = _as_list(spec)
    return [Biolink(category) for category in values] if values else None


def _qualifier_constraints(
    qualifiers: dict[str, str] | None,
) -> list[QualifierConstraint] | None:
    """Build `qualifier_constraints` from a `{qualifier_type: value}` mapping.

    Keys accept bare or `biolink:`-prefixed qualifier types (e.g.
    `object_aspect_qualifier`); values are passed through unchanged.
    """
    if not qualifiers:
        return None
    return [
        QualifierConstraint(
            qualifier_set=[
                Qualifier(qualifier_type_id=Biolink(q_type), qualifier_value=q_value)
                for q_type, q_value in qualifiers.items()
            ]
        )
    ]


def from_qg(
    query_graph: QueryGraph | PathfinderQueryGraph,
    *,
    submitter: str | None = "trapi-testing-tools",
    **body: Any,
) -> Query:
    """Wrap an existing query graph in a `Message` and `Query` to form a query body.

    Args:
        query_graph: The `QueryGraph` (or `PathfinderQueryGraph`) to wrap.
        submitter: Value for the body-level `submitter` field; pass `None` to omit.
        **body: Additional body-level fields passed through to `Query` (e.g.
            `parameters={"tier": 0}`, `bypass_cache=True`, `log_level="INFO"`).

    Returns:
        A `translator_tom.Query` suitable for assigning to a query file's `body`.
    """
    if submitter is not None:
        body["submitter"] = submitter
    return Query(message=Message(query_graph=query_graph), **body)


def one_hop(  # noqa: PLR0913
    subject_category: str | list[str] | None = None,
    object_category: str | list[str] | None = None,
    *,
    subject_ids: str | list[str] | None = None,
    object_ids: str | list[str] | None = None,
    predicate: str | list[str] | None = None,
    inferred: bool = False,
    qualifiers: dict[str, str] | None = None,
    submitter: str | None = "trapi-testing-tools",
    **body: Any,
) -> Query:
    """Build a single-hop TRAPI query: two nodes (`n0` → `n1`) and one edge (`e01`).

    Args:
        subject_category: Category CURIE(s) for the subject node `n0`.
        object_category: Category CURIE(s) for the object node `n1`.
        subject_ids: CURIE(s) pinning the subject node.
        object_ids: CURIE(s) pinning the object node.
        predicate: Predicate CURIE(s) for the edge.
        inferred: If True, sets the edge's `knowledge_type` to "inferred".
        qualifiers: `{qualifier_type: value}` mapping built into the edge's
            `qualifier_constraints`.
        submitter: Value for the body-level `submitter` field; pass `None` to omit.
        **body: Additional body-level fields passed through to `Query` (e.g.
            `parameters={"tier": 0}`, `bypass_cache=True`, `log_level="INFO"`).

    Returns:
        A `translator_tom.Query` suitable for assigning to a query file's `body`.
    """
    predicates = _as_list(predicate)
    edge = QEdge(
        subject="n0",
        object="n1",
        predicates=[Biolink(p) for p in predicates] if predicates else None,
        knowledge_type="inferred" if inferred else None,
        qualifier_constraints=_qualifier_constraints(qualifiers),
    )
    graph = QueryGraph(
        nodes={
            "n0": QNode(
                ids=_as_list(subject_ids), categories=_categories(subject_category)
            ),
            "n1": QNode(
                ids=_as_list(object_ids), categories=_categories(object_category)
            ),
        },
        edges={"e01": edge},
    )
    return from_qg(graph, submitter=submitter, **body)


def load_json(
    path: str | Path,
    model: type[QueryGraph | PathfinderQueryGraph | Message | Query],
    *,
    submitter: str | None = "trapi-testing-tools",
    **body: Any,
) -> Query:
    """Load JSON from `path` as the given TOM `model` and reconstruct a query body.

    Deliberately handles only the common, unambiguous shapes:

    - a bare query graph (`QueryGraph` / `PathfinderQueryGraph`) is wrapped via
      `from_qg`;
    - a `Message` is wrapped in a `Query`;
    - a full `Query` is returned as-is.

    Anything else raises `TypeError`.

    Args:
        path: Path to a JSON file.
        model: The TOM model class the JSON is validated against.
        submitter: Value for the body-level `submitter` field, applied only when a
            `Query` is constructed here (query-graph and `Message` inputs); pass
            `None` to omit. Ignored when the JSON already is a full `Query`.
        **body: Additional body-level fields passed through to the constructed
            `Query`. Ignored when the JSON already is a full `Query`.

    Returns:
        A `translator_tom.Query` suitable for assigning to a query file's `body`.
    """
    loaded = model.from_json(Path(path).read_bytes())
    if isinstance(loaded, Query):
        return loaded
    if isinstance(loaded, Message):
        if submitter is not None:
            body["submitter"] = submitter
        return Query(message=loaded, **body)
    if isinstance(loaded, QueryGraph | PathfinderQueryGraph):
        return from_qg(loaded, submitter=submitter, **body)
    raise TypeError(
        f"Cannot reconstruct a query body from {type(loaded).__name__}; "
        "expected a QueryGraph, PathfinderQueryGraph, Message, or Query."
    )
