import json
from collections.abc import Callable
from contextlib import redirect_stdout
from sys import stderr, stdin
from typing import Annotated

import typer
from InquirerPy.prompts.input import InputPrompt
from rich.console import Console

from trapi_testing_tools.config import CONFIG
from trapi_testing_tools.normalize import (
    normalize_curies,
    render_curies,
    render_names,
    resolve_names,
)
from trapi_testing_tools.utils import is_interactive, maybe_print_traceback

console = Console(stderr=True)
app = typer.Typer(
    no_args_is_help=False,
    context_settings=dict(help_option_names=["-h", "--help"]),
)

DEFAULT_LIMIT = 10  # hits fetched when -n is unset
TOP_N = 5  # rows shown before the "+N More" truncation hint


def _resolve_service_url(app_name: str, level: str) -> str:
    """Resolve a service's base URL for the requested maturity, falling back to prod."""
    instances = CONFIG.environments.get(app_name, {})
    if level in instances:
        return instances[level]

    if level != "prod" and "prod" in instances:
        console.print(
            f"[bright_black]{app_name} has no '{level}' environment; using 'prod' "
            f"(available: {', '.join(instances)})[/]"
        )
        return instances["prod"]

    console.print(
        f"[red]{app_name} has no '{level}' environment "
        f"(available: {', '.join(instances) or 'none'}).[/]"
    )
    raise typer.Exit(1)


def _gather_items(items: list[str] | None, curie: bool) -> list[str]:
    """Collect input items from args, else piped stdin, else an interactive prompt."""
    if items:
        return items

    if not is_interactive():
        raw = stdin.read()
        return (
            raw.split()
            if curie
            else [line.strip() for line in raw.splitlines() if line.strip()]
        )

    with redirect_stdout(stderr):
        text = InputPrompt(
            message="CURIE(s) to normalize:" if curie else "Name to resolve:"
        ).execute()
    text = text.strip()
    return text.split() if curie else ([text] if text else [])


def _fetch[T](action: Callable[[], T]) -> T:
    """Run a fetch, converting any failure into a friendly error and exit."""
    try:
        return action()
    except Exception as error:
        console.print(f"[red]ERROR: normalization request failed: {error!r}[/]")
        maybe_print_traceback()
        raise typer.Exit(1) from error


@app.command("norm | n", help="Resolve names to CURIEs, or normalize CURIEs (with -i).")
def norm(  # noqa: PLR0913
    items: Annotated[
        list[str] | None,
        typer.Argument(
            help="Names to resolve (or CURIEs with -i). "
            "Omit to read stdin or prompt interactively, single-quote to avoid space-splitting."
        ),
    ] = None,
    curie: Annotated[
        bool,
        typer.Option(
            "--id",
            "-i",
            help="Normalize CURIEs (Node Normalizer) instead of resolving names.",
        ),
    ] = False,
    environment: Annotated[
        str,
        typer.Option(
            "--environment",
            "--env",
            "-e",
            help="Service maturity: test (default), ci, dev, or prod.",
        ),
    ] = "test",
    limit: Annotated[
        int | None,
        typer.Option(
            "--limit",
            "-n",
            help="Rows to show — name hits or CURIE equivalents; "
            "default shows the top 5.",
        ),
    ] = None,
    types: Annotated[
        list[str] | None,
        typer.Option(
            "--type",
            "-t",
            help="Filter name hits by Biolink category, repeatable (name mode).",
        ),
    ] = None,
    autocomplete: Annotated[
        bool,
        typer.Option(
            "--autocomplete/--no-autocomplete",
            help="Treat input as an incomplete prefix (name mode).",
        ),
    ] = True,
    conflate: Annotated[
        bool,
        typer.Option(
            "--conflate/--no-conflate",
            "-c/-C",
            help="Apply gene/protein conflation (id mode).",
        ),
    ] = True,
    drug_chemical_conflate: Annotated[
        bool,
        typer.Option(
            "--drug-chemical-conflate",
            "-d",
            help="Apply drug/chemical conflation (id mode).",
        ),
    ] = False,
    raw: Annotated[
        bool,
        typer.Option(
            "--raw",
            "-r",
            help="Print raw service JSON to stdout instead of a table.",
        ),
    ] = False,
) -> None:
    """Resolve names to CURIEs, or normalize CURIEs."""
    resolved = _gather_items(items, curie)
    if not resolved:
        console.print("[red]No input provided.[/]")
        raise typer.Exit(1)

    if curie:
        base_url = _resolve_service_url("nodenorm", environment)
        nodes = _fetch(
            lambda: normalize_curies(
                resolved,
                base_url=base_url,
                conflate=conflate,
                drug_chemical_conflate=drug_chemical_conflate,
            )
        )
        if raw:
            print(json.dumps(nodes))
        else:
            render_curies(nodes, truncate=limit if limit is not None else TOP_N)
    else:
        base_url = _resolve_service_url("nameres", environment)
        fetch_limit = limit if limit is not None else DEFAULT_LIMIT
        hits = _fetch(
            lambda: resolve_names(
                resolved,
                base_url=base_url,
                limit=fetch_limit,
                types=types or [],
                autocomplete=autocomplete,
            )
        )
        if raw:
            print(json.dumps(hits))
        else:
            render_names(hits, resolved, truncate=None if limit is not None else TOP_N)
