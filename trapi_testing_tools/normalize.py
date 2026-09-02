"""Identifier resolution (Name Resolver) and normalization (Node Normalizer).

Fetch helpers return each service's raw JSON verbatim (a `/lookup` list, or the
`get_normalized_nodes` map); render helpers draw to the stderr console. The two are
kept separate so `tt norm --raw` can emit the fetched payload without rendering.
"""

from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from typing import Any

from rich.console import Console
from rich.text import Text

from trapi_testing_tools.utils import SYNC_BASIC_CLIENT, IndentedBlock

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
        with ThreadPoolExecutor(max_workers=min(len(strings), 16)) as pool:
            return dict(zip(strings, pool.map(lookup, strings), strict=True))


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


# Extra indent for secondary info lines, aligning them under the row content past "N. ".
# The block's `│ ` gutter is added by `IndentedBlock`, so wrapped lines keep it too.
_INNER = "   "


@contextmanager
def _indented_block() -> Iterator[None]:
    """Within the block, ``console`` prints get a ``│ `` gutter on every wrapped line."""
    console.push_render_hook(IndentedBlock())
    try:
        yield
    finally:
        console.pop_render_hook()


def _close_line(shown: int, total: int, *, empty: str) -> str:
    """Markup for a block's closing ``└`` summary: "+N more" hint, empty note, or count."""
    hidden = total - shown
    if hidden > 0:
        return f"[white]+{hidden} more[/] [bright_black](use -n {total} to see all)[/]"
    if total == 0:
        return f"[bright_black]{empty}[/]"
    return f"[bright_black]all {total} shown[/]"


def render_names(
    payload: list[dict[str, Any]] | dict[str, list[dict[str, Any]]],
    queries: list[str],
    *,
    truncate: int | None = None,
) -> None:
    """Render name-resolution hits as an indented block per input string.

    ``truncate`` caps each block at that many rows, closing with a "+N more" hint.
    """
    pairs = (
        [(queries[0], payload)] if isinstance(payload, list) else list(payload.items())
    )

    for query, hits in pairs:
        count = len(hits)
        noun = "result" if count == 1 else "results"
        console.print(Text(f'┌ "{query}" · {count} {noun}', style="rule.line"))

        shown = hits[:truncate] if truncate is not None else hits
        with _indented_block():
            for index, hit in enumerate(shown, start=1):
                categories = hit.get("types") or []
                score = hit.get("score")
                clique = hit.get("clique_identifier_count")
                curie = hit.get("curie") or "—"
                label = hit.get("label") or "—"
                category = _bare(categories[0]) if categories else "—"
                score_text = f"{score:.2f}" if isinstance(score, int | float) else "—"
                clique_text = str(clique) if clique is not None else "—"
                synonyms = _preview_synonyms(hit.get("synonyms") or [])

                console.print(Text(f"{index}. {curie} · {label}", style="white"))
                console.print(
                    Text(
                        f"{_INNER}{category} · Score: {score_text} · Clique: {clique_text}",
                        style="bright_black",
                    )
                )
                console.print(
                    Text(f"{_INNER}Synonyms: {synonyms}", style="bright_black")
                )

        console.print(
            f"└ {_close_line(len(shown), count, empty='no matches')}",
            style="rule.line",
            markup=True,
        )


def render_curies(
    payload: dict[str, dict[str, Any] | None], *, truncate: int | None = None
) -> None:
    """Render normalized CURIEs: a detail block for one, a summary block for many.

    ``truncate`` caps the single-CURIE equivalents list, closing with a "+N more" hint.
    """
    entries = list(payload.items())
    if len(entries) == 1:
        _render_curie_detail(*entries[0], truncate=truncate)
        return

    console.print(Text(f"┌ normalized · {len(entries)} inputs", style="rule.line"))
    with _indented_block():
        for index, (curie, node) in enumerate(entries, start=1):
            if not node:
                console.print(Text(f"{index}. {curie} → no match", style="white"))
                continue
            identifier = node.get("id") or {}
            canonical = identifier.get("identifier") or "—"
            label = identifier.get("label") or "—"
            categories = [_bare(c) for c in (node.get("type") or [])]
            equiv_count = len(node.get("equivalent_identifiers") or [])
            console.print(
                Text(f"{index}. {curie} → {canonical} · {label}", style="white")
            )
            console.print(
                Text(
                    f"{_INNER}{', '.join(categories) or '—'} · {equiv_count} equivalents",
                    style="bright_black",
                )
            )

    matched = sum(1 for _, node in entries if node)
    console.print(
        f"└ [bright_black]{matched}/{len(entries)} normalized[/]",
        style="rule.line",
        markup=True,
    )


def _render_curie_detail(
    curie: str, node: dict[str, Any] | None, *, truncate: int | None = None
) -> None:
    """Render one normalized CURIE as an indented block: node summary + equivalents."""
    if not node:
        console.print(Text(f"┌ {curie}", style="rule.line"))
        console.print("└ [bright_black]no match[/]", style="rule.line", markup=True)
        return

    identifier = node.get("id") or {}
    label = identifier.get("label") or "—"
    categories = [_bare(c) for c in (node.get("type") or [])]
    info_content = node.get("information_content")
    ic_text = str(info_content) if info_content is not None else "—"
    equivalents = node.get("equivalent_identifiers") or []
    total = len(equivalents)

    noun = "equivalent" if total == 1 else "equivalents"
    console.print(Text(f"┌ {curie} · {total} {noun}", style="rule.line"))

    shown = equivalents[:truncate] if truncate is not None else equivalents
    with _indented_block():
        console.print(
            Text(
                f"{label} · IC: {ic_text} · {', '.join(categories) or '—'}",
                style="bright_black",
            )
        )
        for index, equivalent in enumerate(shown, start=1):
            eq_id = equivalent.get("identifier") or "—"
            eq_label = equivalent.get("label") or "—"
            console.print(Text(f"{index}. {eq_id} · {eq_label}", style="white"))

    console.print(
        f"└ {_close_line(len(shown), total, empty='no equivalents')}",
        style="rule.line",
        markup=True,
    )
