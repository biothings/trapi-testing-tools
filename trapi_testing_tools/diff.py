"""TRAPI-aware structural diff of two TRAPI responses.

Rendering and reporting layer over TOM's ``diff`` (TOM 2.0), dispatched per TRAPI version
(``translator_tom.v1_6`` / ``v2_0`` via :func:`trapi_testing_tools.trapi_models.models`),
which does the TRAPI-aware, order-insensitive delta diffing this module used to implement
by hand. TOM normalizes both responses (KG edges re-keyed by ``Edge.hash()`` and every
binding / aux-graph reference remapped, so arbitrary per-service edge ids stop mattering),
aligns unordered collections (results, attributes, sources, analyses, categories, …) by
member identity rather than by position, and returns typed ``Delta`` objects — ``added`` /
``removed`` / ``changed`` / ``reordered`` — each with a structural ``path`` and a human
``locator`` (``Delta`` and ``Response`` are structurally identical across versions, so the
grouping and rendering below are version-agnostic).

Two modes map onto TOM's ``strict`` flag:

- **structural** (default, ``strict=True``): descend fully and report every field-level
  difference, including attributes, provenance, and scores.
- **identity** (``strict=False``): short-circuit any subtree whose TRAPI ``.hash()``
  matches, reporting only membership changes and deliberately ignoring
  attribute / provenance / **score** changes.

This module's job is presentation: group TOM's flat deltas into report sections
(query_graph, results, KG nodes, KG edges, auxiliary_graphs, and response-level "other")
and render them three ways — a rich stderr summary, a compact git-diff-style plaintext
report (the default output), and a machine-readable JSON report (``--json``). TOM diffs
*every* field, including response-level extras such as ``job_id`` and ``submitter``; those
surface under the "response" section and are expected to differ between runs.
"""

import json
from typing import Any

from rich.console import Console
from rich.markup import escape
from rich.text import Text
from translator_tom.v1_6 import Delta, Response  # Delta/Response are version-identical

from trapi_testing_tools.trapi_models import TrapiVersion, models
from trapi_testing_tools.utils import IndentedBlock

console = Console(stderr=True)

_KINDS = ("added", "removed", "changed", "reordered")
KIND_MARKER = {"added": "+", "removed": "-", "changed": "~", "reordered": "⇄"}
KIND_STYLE = {
    "added": "green",
    "removed": "red",
    "changed": "yellow",
    "reordered": "cyan",
}

# Cap the number of individual differences listed per section in the rich stderr view.
MAX_SHOWN = 25

# Report sections, in display order, with a human label each.
SECTION_ORDER = (
    "query_graph",
    "results",
    "nodes",
    "edges",
    "auxiliary_graphs",
    "other",
)
SECTION_LABEL = {
    "query_graph": "query_graph",
    "results": "results",
    "nodes": "knowledge_graph.nodes",
    "edges": "knowledge_graph.edges",
    "auxiliary_graphs": "auxiliary_graphs",
    "other": "response",
}
# Section = first matching path prefix (stripped for the locator); unmatched paths → "other".
_SECTION_PREFIXES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("query_graph", ("message", "query_graph")),
    ("results", ("message", "results")),
    ("nodes", ("message", "knowledge_graph", "nodes")),
    ("edges", ("message", "knowledge_graph", "edges")),
    ("auxiliary_graphs", ("message", "auxiliary_graphs")),
)


def diff_responses(
    left: Response,
    right: Response,
    *,
    strict: bool = True,
    version: TrapiVersion | None = None,
) -> list[Delta]:
    """Diff two TRAPI responses via TOM: TRAPI-aware and order-insensitive.

    Delegates to the ``diff`` of the ``version``-appropriate TOM namespace (``v1_6`` /
    ``v2_0``) with ``normalize=True``, so both responses are normalized on deep copies
    (edges re-keyed by hash, references remapped) and compare regardless of each service's
    edge ids; the caller's objects aren't mutated.
    """
    deltas = models(version).diff(left, right, strict=strict, normalize=True)
    # Drop TOM's vacuous `changed` deltas for response-level extras (left == right).
    return [d for d in deltas if not (d.kind == "changed" and d.left == d.right)]


def _classify(path: tuple[str | int, ...]) -> tuple[str, tuple[str | int, ...]]:
    """Map a delta ``path`` to its report section and the path relative to that section."""
    for section, prefix in _SECTION_PREFIXES:
        if path[: len(prefix)] == prefix:
            return section, path[len(prefix) :]
    return "other", path


def _group(deltas: list[Delta]) -> dict[str, list[tuple[tuple[str | int, ...], Delta]]]:
    """Group deltas by section (in ``SECTION_ORDER``), pairing each with its relative path."""
    groups: dict[str, list[tuple[tuple[str | int, ...], Delta]]] = {
        section: [] for section in SECTION_ORDER
    }
    for delta in deltas:
        section, rest = _classify(delta.path)
        groups[section].append((rest, delta))
    return groups


def _counts(entries: list[tuple[tuple[str | int, ...], Delta]]) -> dict[str, int]:
    """Count a section's deltas by kind."""
    counts = dict.fromkeys(_KINDS, 0)
    for _, delta in entries:
        counts[delta.kind] += 1
    return counts


def _totals(
    groups: dict[str, list[tuple[tuple[str | int, ...], Delta]]],
) -> dict[str, int]:
    """Sum per-section counts into overall totals by kind."""
    totals = dict.fromkeys(_KINDS, 0)
    for entries in groups.values():
        for kind, count in _counts(entries).items():
            totals[kind] += count
    return totals


def _location(rest: tuple[str | int, ...]) -> str:
    """Render a relative path as a readable, section-relative locator."""
    return " / ".join(str(seg) for seg in rest)


def _flatten(value: object) -> str:
    """A one-line (untruncated) string for a value."""
    text = value if isinstance(value, str) else json.dumps(value, default=str)
    return text.replace("\n", " ")


def _short(value: object, limit: int = 60) -> str:
    """A compact, truncated one-line string for a value, for the human views."""
    text = _flatten(value)
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _content_lines(value: object, marker: str) -> list[str]:
    """Pretty-printed JSON of a value, indented and git-style prefixed with ``marker``."""
    text = json.dumps(value, indent=2, default=str)
    return [f"{marker}   {line}" for line in text.splitlines()]


def _counts_text(counts: dict[str, int]) -> str:
    """Plain ``+a -r ~c`` counts for headers, appending ``⇄n`` only when reorders exist."""
    text = f"+{counts['added']} -{counts['removed']} ~{counts['changed']}"
    if counts["reordered"]:
        text += f" ⇄{counts['reordered']}"
    return text


def _counts_markup(counts: dict[str, int]) -> str:
    """Rich-markup, colored counts for headers, appending ``⇄n`` only when reorders exist."""
    text = (
        f"[green]+{counts['added']}[/] [red]-{counts['removed']}[/] "
        f"[yellow]~{counts['changed']}[/]"
    )
    if counts["reordered"]:
        text += f" [cyan]⇄{counts['reordered']}[/]"
    return text


def build_report(deltas: list[Delta], *, strict: bool) -> dict[str, Any]:
    """Assemble the machine-readable JSON diff report from TOM deltas."""
    groups = _group(deltas)
    entries_out: list[dict[str, Any]] = []
    for section in SECTION_ORDER:
        for rest, delta in groups[section]:
            entry: dict[str, Any] = {
                "section": section,
                "location": _location(rest),
                "path": list(delta.path),
                "kind": delta.kind,
            }
            if delta.locator is not None:
                entry["locator"] = delta.locator
            if delta.kind != "added":
                entry["left"] = delta.left
            if delta.kind != "removed":
                entry["right"] = delta.right
            entries_out.append(entry)
    return {
        "summary": {
            "identical": not deltas,
            "mode": "structural" if strict else "identity",
            "total_differences": len(deltas),
            "sections": {s: _counts(entries) for s, entries in groups.items()},
        },
        "differences": entries_out,
    }


def _text_entry(rest: tuple[str | int, ...], delta: Delta, *, full: bool) -> list[str]:
    """The plaintext line(s) for one delta (with inline content when ``full``)."""
    marker = KIND_MARKER[delta.kind]
    location = _location(rest)

    if delta.kind == "reordered":
        lines = [f"{marker} {location or '(members)'}: order changed"]
        if full:
            lines.append(f"-   {_flatten(delta.left)}")
            lines.append(f"+   {_flatten(delta.right)}")
        return lines

    if delta.kind == "changed":
        # A leaf scalar change is shown inline; objects only expand under ``full``.
        if not isinstance(delta.left, dict | list) and not isinstance(
            delta.right, dict | list
        ):
            left = _flatten(delta.left) if full else _short(delta.left)
            right = _flatten(delta.right) if full else _short(delta.right)
            return [f"{marker} {location}: {left} -> {right}"]
        lines = [f"{marker} {location}"]
        if full:
            lines.extend(_content_lines(delta.left, "-"))
            lines.extend(_content_lines(delta.right, "+"))
        return lines

    # added / removed: the value lives on the corresponding side.
    value = delta.right if delta.kind == "added" else delta.left
    if not full:
        return [f"{marker} {location}"]
    if isinstance(value, dict | list):
        return [f"{marker} {location}", *_content_lines(value, marker)]
    return [f"{marker} {location}: {_flatten(value)}"]


def render_text_report(
    deltas: list[Delta],
    *,
    strict: bool,
    left_name: str,
    right_name: str,
    full: bool = False,
) -> str:
    """Render a compact, git-diff-style plaintext report (for piping/saving/viewing).

    With ``full``, added/removed/changed values are expanded inline (scalars untruncated,
    objects as marker-prefixed JSON blocks) instead of showing only the locator.
    """
    groups = _group(deltas)
    mode = "structural" if strict else "identity"
    lines = [f"--- {left_name}", f"+++ {right_name}", f"# mode: {mode}"]
    if not deltas:
        lines.append("# responses are identical")
        return "\n".join(lines)

    for section in SECTION_ORDER:
        entries = groups[section]
        if not entries:
            continue
        lines.append("")
        lines.append(
            f"@@ {SECTION_LABEL[section]}  {_counts_text(_counts(entries))} @@"
        )
        for rest, delta in entries:
            lines.extend(_text_entry(rest, delta, full=full))

    lines.append("")
    lines.append(f"# {_counts_text(_totals(groups))} (left = baseline, right = new)")
    return "\n".join(lines)


def _diff_line(rest: tuple[str | int, ...], delta: Delta) -> str:
    """A one-line, markup-escaped rendering of a single delta."""
    marker = KIND_MARKER[delta.kind]
    style = KIND_STYLE[delta.kind]
    location = escape(_location(rest))
    if delta.kind == "reordered":
        return (
            f"[{style}]{marker}[/] {location or '(members)'}  "
            "[bright_black]order changed[/]"
        )
    detail = ""
    if delta.kind == "changed" and not isinstance(delta.left, dict | list):
        detail = (
            f"  {escape(_short(delta.left))} [bright_black]→[/] "
            f"{escape(_short(delta.right))}"
        )
    return f"[{style}]{marker}[/] {location}{detail}"


def render_report(deltas: list[Delta], *, strict: bool) -> None:
    """Render the diff to stderr, grouped by section, in the house frame."""
    groups = _group(deltas)
    mode = "structural" if strict else "identity"
    console.rule(Text("┌ ", style="rule.line") + f"Diff ({mode})", align="left")
    console.push_render_hook(IndentedBlock())
    try:
        if not deltas:
            console.print("[green]Responses are identical.[/]", highlight=False)
        for section in SECTION_ORDER:
            entries = groups[section]
            if not entries:
                continue
            console.print(
                f"[bold]{escape(SECTION_LABEL[section])}[/]  "
                f"{_counts_markup(_counts(entries))}",
                highlight=False,
            )
            for rest, delta in entries[:MAX_SHOWN]:
                console.print(f"  {_diff_line(rest, delta)}", highlight=False)
            if len(entries) > MAX_SHOWN:
                console.print(
                    f"  [bright_black]… {len(entries) - MAX_SHOWN} more[/]",
                    highlight=False,
                )
    finally:
        console.pop_render_hook()

    totals = _totals(groups)
    verdict = "[green]identical[/]" if not deltas else _counts_markup(totals)
    console.print(
        f"[rule.line]└[/] {verdict}  [bright_black](left = baseline, right = new)[/]",
        markup=True,
        highlight=False,
    )
