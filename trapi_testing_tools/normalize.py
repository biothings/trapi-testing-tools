"""Identifier resolution (Name Resolver) and normalization (Node Normalizer).

Fetch helpers return each service's raw JSON verbatim (a `/lookup` list, or the
`get_normalized_nodes` map); render helpers draw tables to the stderr console. The two are
kept separate so `tt norm --raw` can emit the fetched payload without rendering.
"""

from typing import Any

from rich import box
from rich.console import Console
from rich.table import Table

from trapi_testing_tools.utils import SYNC_BASIC_CLIENT

console = Console(stderr=True)

TIMEOUT = 30


def _bare(category: str) -> str:
    """Strip the ``biolink:`` prefix from a category for display."""
    return category.removeprefix("biolink:")


def resolve_names(
    strings: list[str],
    *,
    base_url: str,
    limit: int,
    types: list[str],
    autocomplete: bool,
) -> list[dict[str, Any]] | dict[str, list[dict[str, Any]]]:
    """Resolve names to CURIEs via Name Resolver's ``/lookup``.

    A single name returns that endpoint's raw hit list; multiple names loop ``/lookup``
    (the Translator-hosted instance has no bulk endpoint) into a ``{name: hits}`` map.
    """
    biolink_types = [t if t.startswith("biolink:") else f"biolink:{t}" for t in types]
    lookup_url = f"{base_url.rstrip('/')}/lookup"

    def lookup(string: str) -> list[dict[str, Any]]:
        params: dict[str, Any] = {
            "string": string,
            "limit": limit,
            "autocomplete": "true" if autocomplete else "false",
        }
        if biolink_types:
            params["biolink_type"] = biolink_types
        response = SYNC_BASIC_CLIENT.get(lookup_url, params=params, timeout=TIMEOUT)
        response.raise_for_status()
        return response.json()

    with console.status("Resolving names..."):
        if len(strings) == 1:
            return lookup(strings[0])
        return {string: lookup(string) for string in strings}


def normalize_curies(
    curies: list[str],
    *,
    base_url: str,
    conflate: bool,
    drug_chemical_conflate: bool,
) -> dict[str, dict[str, Any] | None]:
    """Normalize CURIEs via Node Normalizer, returning the raw ``{curie: node|null}`` map."""
    body = {
        "curies": curies,
        "conflate": conflate,
        "drug_chemical_conflate": drug_chemical_conflate,
    }

    with console.status("Normalizing CURIEs..."):
        response = SYNC_BASIC_CLIENT.post(
            f"{base_url.rstrip('/')}/get_normalized_nodes",
            json=body,
            timeout=TIMEOUT,
        )
    response.raise_for_status()
    return response.json()


def _preview_synonyms(synonyms: list[str], limit: int = 3) -> str:
    """A short, comma-joined synonym sample with an overflow count."""
    if not synonyms:
        return "—"
    shown = ", ".join(synonyms[:limit])
    return f"{shown} …(+{len(synonyms) - limit})" if len(synonyms) > limit else shown


def render_names(
    payload: list[dict[str, Any]] | dict[str, list[dict[str, Any]]],
    queries: list[str],
    *,
    truncate: int | None = None,
) -> None:
    """Render name-resolution hits, one table per input string.

    ``truncate`` caps each table at that many rows, appending a "+N More" hint.
    """
    pairs = (
        [(queries[0], payload)] if isinstance(payload, list) else list(payload.items())
    )

    for query, hits in pairs:
        if not hits:
            console.print(f'[bright_black]no matches for "{query}"[/]')
            continue

        shown = hits[:truncate] if truncate is not None else hits

        table = Table(title=f'"{query}"', title_style="bold", box=box.SIMPLE)
        table.add_column("CURIE", overflow="fold")
        table.add_column("Label", overflow="fold")
        table.add_column("Category")
        table.add_column("Score", justify="right")
        table.add_column("Synonyms", overflow="fold")
        table.add_column("Clique", justify="right")

        for hit in shown:
            categories = hit.get("types") or []
            score = hit.get("score")
            clique = hit.get("clique_identifier_count")
            table.add_row(
                hit.get("curie") or "—",
                hit.get("label") or "—",
                _bare(categories[0]) if categories else "—",
                f"{score:.2f}" if isinstance(score, int | float) else "—",
                _preview_synonyms(hit.get("synonyms") or []),
                str(clique) if clique is not None else "—",
            )
        console.print(table)

        hidden = len(hits) - len(shown)
        if hidden > 0:
            console.print(
                f"  [white]+{hidden} More[/] "
                f"[bright_black](use -n {len(hits)} to see all)[/]"
            )


def render_curies(payload: dict[str, dict[str, Any] | None]) -> None:
    """Render normalized CURIEs: a detail view for one, a summary table for many."""
    entries = list(payload.items())
    if len(entries) == 1:
        _render_curie_detail(*entries[0])
        return

    table = Table(title="Normalized CURIEs", title_style="bold", box=box.SIMPLE)
    table.add_column("Input", overflow="fold")
    table.add_column("Canonical", overflow="fold")
    table.add_column("Label", overflow="fold")
    table.add_column("Categories", overflow="fold")
    table.add_column("Equiv.", justify="right")

    for curie, node in entries:
        if not node:
            table.add_row(curie, "[bright_black]— no match[/]", "—", "—", "—")
            continue
        identifier = node.get("id") or {}
        categories = [_bare(c) for c in (node.get("type") or [])]
        table.add_row(
            curie,
            identifier.get("identifier") or "—",
            identifier.get("label") or "—",
            ", ".join(categories) if categories else "—",
            str(len(node.get("equivalent_identifiers") or [])),
        )
    console.print(table)


def _render_curie_detail(curie: str, node: dict[str, Any] | None) -> None:
    """Render one normalized CURIE as a metadata table plus its equivalents."""
    if not node:
        console.print(f"[bright_black]no match for {curie}[/]")
        return

    identifier = node.get("id") or {}
    categories = [_bare(c) for c in (node.get("type") or [])]
    info_content = node.get("information_content")

    meta = Table(
        title=f"Normalized {curie}",
        title_style="bold",
        box=box.SIMPLE,
        show_header=False,
    )
    meta.add_column("Field", style="rule.line", justify="right")
    meta.add_column("Value", overflow="fold")
    meta.add_row("Canonical", identifier.get("identifier") or "—")
    meta.add_row("Label", identifier.get("label") or "—")
    meta.add_row("Categories", ", ".join(categories) if categories else "—")
    meta.add_row("Info Content", str(info_content) if info_content is not None else "—")
    console.print(meta)

    equivalents = node.get("equivalent_identifiers") or []
    eq_table = Table(
        title=f"Equivalent identifiers ({len(equivalents)})",
        title_style="bold",
        box=box.SIMPLE,
    )
    eq_table.add_column("Identifier", overflow="fold")
    eq_table.add_column("Label", overflow="fold")
    for equivalent in equivalents:
        eq_table.add_row(
            equivalent.get("identifier") or "—", equivalent.get("label") or "—"
        )
    console.print(eq_table)
