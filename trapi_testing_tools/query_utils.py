"""Convenience constructors for building TRAPI query bodies with translator_tom."""

from typing import Any

from translator_tom import (
    Biolink,
    Message,
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
    if submitter is not None:
        body["submitter"] = submitter
    return Query(message=Message(query_graph=graph), **body)
