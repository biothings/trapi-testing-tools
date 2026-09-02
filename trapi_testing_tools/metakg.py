"""Meta knowledge graph support checks against a TRAPI service.

Fetch the service's `meta_knowledge_graph`, then decide whether it can answer a given
edge. Matching is hierarchy-aware (query categories/predicates are expanded to their
Biolink descendants, since the metakg lists only most-specific terms) and honors
symmetric/inverse predicates. Fetch/match/render are kept separate so `tt metakg --raw`
can emit results without rendering.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

import httpx
from rich.console import Console
from rich.text import Text
from translator_tom import Biolink

from trapi_testing_tools.trapi_models import TrapiVersion, models
from trapi_testing_tools.utils import SYNC_BASIC_CLIENT

console = Console(stderr=True)

TIMEOUT = 30


@dataclass
class EdgeSpec:
    """One edge to check: category/predicate lists (empty = wildcard) plus constraints."""

    subjects: list[str]
    predicates: list[str]
    objects: list[str]
    qualifier_constraints: list[Any] = field(default_factory=list)
    attribute_types: list[str] = field(default_factory=list)
    source: str | None = None
    note: str | None = None


@dataclass
class Support:
    """The verdict for one `EdgeSpec` against a metakg."""

    spec: EdgeSpec
    supported: bool
    reason: str | None = None
    attribute_hits: dict[str, bool | None] = field(default_factory=dict)


def fetch_metakg(base_url: str) -> httpx.Response:
    """GET the service's `meta_knowledge_graph`, raising on a non-2xx status."""
    with console.status("Fetching meta_knowledge_graph..."):
        response = SYNC_BASIC_CLIENT.get(
            f"{base_url.rstrip('/')}/meta_knowledge_graph", timeout=TIMEOUT
        )
    response.raise_for_status()
    return response


def parse_metakg(response: httpx.Response, version: TrapiVersion) -> Any:
    """Parse a metakg response into the TOM `MetaKnowledgeGraph` for `version`."""
    return models(version).MetaKnowledgeGraph.from_json(response.content)


def parse_qualifier_flags(values: list[str], version: TrapiVersion) -> list[Any]:
    """Build a single `QualifierConstraint` from `-q TYPE:VALUE` flags (all must hold)."""
    if not values:
        return []

    qualifier_cls = models(version).Qualifier
    constraint_cls = models(version).QualifierConstraint

    qualifiers = []
    for value in values:
        # Drop a leading biolink: then split on the first colon, keeping CURIE-valued values intact.
        type_part, sep, qual_value = value.removeprefix("biolink:").partition(":")
        if not sep or not qual_value:
            raise ValueError(f"Qualifier must be TYPE:VALUE, got {value!r}.")
        qualifiers.append(
            qualifier_cls(
                qualifier_type_id=Biolink(type_part), qualifier_value=qual_value
            )
        )

    return [constraint_cls(qualifier_set=qualifiers)]


def extract_edges(
    query_graph: dict[str, Any], version: TrapiVersion, source: str
) -> list[EdgeSpec]:
    """Turn a query graph's edges into `EdgeSpec`s (skips pathfinder path graphs)."""
    if "edges" not in query_graph:
        console.print(f"[bright_black]{source}: no query-graph edges, skipping.[/]")
        return []

    graph = models(version).QueryGraph.from_dict(query_graph)

    specs = []
    for edge_id, qedge in graph.edges.items():
        subject_node = graph.nodes.get(qedge.subject)
        object_node = graph.nodes.get(qedge.object)
        subjects = list(subject_node.categories_list) if subject_node else []
        objects = list(object_node.categories_list) if object_node else []

        notes = [
            f"{role} {node_id} has ids but no category — treated as wildcard"
            for role, node_id, node, cats in (
                ("subject", qedge.subject, subject_node, subjects),
                ("object", qedge.object, object_node, objects),
            )
            if node and not cats and node.ids_list
        ]

        specs.append(
            EdgeSpec(
                subjects=subjects,
                predicates=list(qedge.predicates_list),
                objects=objects,
                qualifier_constraints=list(qedge.qualifier_constraints_list),
                attribute_types=[c.id for c in qedge.attribute_constraints_list],
                source=f"{source}:{edge_id}",
                note="; ".join(notes) or None,
            )
        )

    return specs


def _attr_hit(metaedge: Any, attribute_type: str) -> bool | None:
    """The offered attribute's `constraint_use`, or None if the edge doesn't offer it."""
    candidates = {attribute_type}
    if ":" not in attribute_type:
        candidates.add(Biolink(attribute_type))
    for attribute in metaedge.attributes_list:
        if attribute.attribute_type_id in candidates:
            return attribute.constraint_use
    return None


def _invert_quals(constraints: list[Any]) -> list[Any] | None:
    """Invert qualifier constraints for a reversed edge, or None if any can't invert."""
    inverted = []
    for constraint in constraints:
        try:
            inverted.append(constraint.get_inverse())
        except (ValueError, AttributeError):
            return None
    return inverted


def _orientations(
    subject_set: set[str] | None,
    predicate_set: set[str] | None,
    object_set: set[str] | None,
    predicates: list[str],
    quals: list[Any],
) -> Iterator[tuple[set[str] | None, set[str] | None, set[str] | None, list[Any]]]:
    """Yield the SPO/qualifier orientations to try (forward, then symmetric/inverse)."""
    yield subject_set, predicate_set, object_set, quals
    if not predicates:
        return

    if any(Biolink.is_symmetric(predicate) for predicate in predicates):
        yield object_set, predicate_set, subject_set, quals

    inverses = {
        inverse
        for predicate in predicates
        if (inverse := Biolink.get_inverse(predicate)) is not None
    }
    if inverses:
        inverse_quals = _invert_quals(quals)
        if inverse_quals is not None:
            yield object_set, Biolink.expand(inverses), subject_set, inverse_quals


def _match(  # noqa: PLR0913
    subject_set: set[str] | None,
    predicate_set: set[str] | None,
    object_set: set[str] | None,
    metaedges: list[Any],
    quals: list[Any],
    attribute_types: list[str],
) -> tuple[bool, dict[str, bool | None]]:
    """Find a metaedge matching SPO, the qualifier constraints, and all attributes."""
    for metaedge in metaedges:
        if subject_set is not None and metaedge.subject not in subject_set:
            continue
        if predicate_set is not None and metaedge.predicate not in predicate_set:
            continue
        if object_set is not None and metaedge.object not in object_set:
            continue
        if quals and not metaedge.meets_qualifier_constraints(quals):
            continue
        hits = {attr: _attr_hit(metaedge, attr) for attr in attribute_types}
        if attribute_types and any(hit is None for hit in hits.values()):
            continue
        return True, hits
    return False, {}


def _explain_miss(
    spec: EdgeSpec,
    metaedges: list[Any],
    subject_set: set[str] | None,
    predicate_set: set[str] | None,
    object_set: set[str] | None,
) -> str:
    """A short reason the edge is unsupported (which dimension/constraint failed)."""
    spo = [
        metaedge
        for metaedge in metaedges
        if (subject_set is None or metaedge.subject in subject_set)
        and (predicate_set is None or metaedge.predicate in predicate_set)
        and (object_set is None or metaedge.object in object_set)
    ]

    if not spo:
        dims = [
            (name, values, attr)
            for name, values, attr in (
                ("subject category", subject_set, "subject"),
                ("predicate", predicate_set, "predicate"),
                ("object category", object_set, "object"),
            )
            if values is not None
            and not any(getattr(me, attr) in values for me in metaedges)
        ]
        if dims:
            return "no MetaEdge with " + ", ".join(name for name, _, _ in dims)
        return "no MetaEdge combines given subject, predicate, object"

    if spec.qualifier_constraints:
        return "no matching MetaEdge offers given qualifier(s)"

    missing = [
        attr
        for attr in spec.attribute_types
        if all(_attr_hit(me, attr) is None for me in spo)
    ]
    if missing:
        return "no matching MetaEdge offers attribute(s): " + ", ".join(missing)
    return "no matching MetaEdge"


def edge_supported(spec: EdgeSpec, metaedges: list[Any]) -> Support:
    """Whether the metakg supports `spec`, hierarchy-aware and orientation-aware."""
    subject_set = Biolink.expand(set(spec.subjects)) if spec.subjects else None
    predicate_set = Biolink.expand(set(spec.predicates)) if spec.predicates else None
    object_set = Biolink.expand(set(spec.objects)) if spec.objects else None

    for subjects, predicates, objects, quals in _orientations(
        subject_set, predicate_set, object_set, spec.predicates, spec.qualifier_constraints
    ):
        matched, hits = _match(
            subjects, predicates, objects, metaedges, quals, spec.attribute_types
        )
        if matched:
            return Support(spec, True, None, hits)

    reason = _explain_miss(spec, metaedges, subject_set, predicate_set, object_set)
    return Support(spec, False, reason, {})


def _bare(term: str) -> str:
    """Strip the ``biolink:`` prefix for display."""
    return term.removeprefix("biolink:")


def _triple(spec: EdgeSpec) -> str:
    """A compact ``Subject->predicate->Object`` label (``*`` for a wildcard dimension)."""
    parts = [
        "|".join(_bare(term) for term in terms) or "*"
        for terms in (spec.subjects, spec.predicates, spec.objects)
    ]
    return " -> ".join(parts)


def _tree(nodes: list[tuple[str, list[str]]]) -> list[str]:
    """Render (label, children) nodes as box-drawing tree lines, children one level in."""
    lines = []
    for index, (label, children) in enumerate(nodes):
        last = index == len(nodes) - 1
        lines.append(f"[bright_black]{'└─' if last else '├─'}[/] {label}")
        guide = "   " if last else "[bright_black]│[/]  "
        for child_index, child in enumerate(children):
            branch = "└─" if child_index == len(children) - 1 else "├─"
            lines.append(f"{guide}[bright_black]{branch}[/] {child}")
    return lines


def _detail_lines(support: Support) -> list[str]:
    """Tree lines under an edge: qualifiers/attributes groups, note, then miss reason."""
    spec = support.spec
    nodes: list[tuple[str, list[str]]] = []

    if spec.qualifier_constraints:
        nodes.append(
            (
                "[bright_black]qualifiers[/]",
                [
                    f"{_bare(qual.qualifier_type_id)}={qual.qualifier_value}"
                    for constraint in spec.qualifier_constraints
                    for qual in constraint.qualifier_set
                ],
            )
        )
    if spec.attribute_types:
        nodes.append(
            (
                "[bright_black]attributes[/]",
                [
                    f"{_bare(attr)}"
                    f"{' (constrainable)' if support.attribute_hits.get(attr) else ''}"
                    for attr in spec.attribute_types
                ],
            )
        )
    if spec.note:
        nodes.append((f"[yellow]! {spec.note}[/]", []))
    if not support.supported and support.reason:
        nodes.append((f"[red]{support.reason}[/]", []))

    return _tree(nodes)


def _support_json(support: Support) -> dict[str, Any]:
    spec = support.spec
    return {
        "source": spec.source,
        "subject": spec.subjects,
        "predicate": spec.predicates,
        "object": spec.objects,
        "qualifiers": [c.to_dict() for c in spec.qualifier_constraints],
        "attributes": spec.attribute_types,
        "supported": support.supported,
        "attribute_offered": support.attribute_hits,
        "reason": support.reason,
    }


def render_support(results: list[Support], env: str, *, raw: bool) -> None:
    """Emit results as JSON to stdout (`raw`), else ping-style framed groups to stderr."""
    if raw:
        print(json.dumps([_support_json(support) for support in results]))
        return

    groups: dict[str | None, list[Support]] = {}
    for support in results:
        source = support.spec.source
        key = source.rsplit(":", 1)[0] if source else None
        groups.setdefault(key, []).append(support)

    for key, group in groups.items():
        console.print(Text("┌ ", style="rule.line") + (f"{key} · {env}" if key else env))

        for support in group:
            source = support.spec.source
            mark = "[green]✓[/]" if support.supported else "[red]✗[/]"
            label = f"{source.rsplit(':', 1)[1]}: " if source else ""
            console.print(f"[rule.line]│[/] {mark} {label}{_triple(support.spec)}")
            for line in _detail_lines(support):
                console.print(f"[rule.line]│[/]   {line}")

        supported = sum(1 for support in group if support.supported)
        total = len(group)
        if supported == total:
            summary = "[green]✓ All supported[/]"
        elif supported == 0:
            summary = f"[red]{supported}/{total} supported[/]"
        else:
            summary = f"[yellow]{supported}/{total} supported[/]"
        console.print(f"└ {summary}", style="rule.line", markup=True)
