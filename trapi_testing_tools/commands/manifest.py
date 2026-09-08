import json
import sys
from enum import Enum
from typing import Annotated

import typer
from rich.console import Console

from trapi_testing_tools.manifest import build_manifest, render_manifest

console = Console(stderr=True)
app = typer.Typer(
    no_args_is_help=False,
    context_settings=dict(help_option_names=["-h", "--help"]),
)


class Domain(str, Enum):
    """Which slice of the capability surface to emit (default: all)."""

    all = "all"
    envs = "envs"
    analyses = "analyses"
    queries = "queries"
    tests = "tests"
    config = "config"


@app.command(
    "manifest | man",
    help="Show a manifest of runtime-resolved capabilities (see domain).",
)
def manifest(
    domain: Annotated[
        Domain,
        typer.Argument(help="Which domain to show; defaults to all."),
    ] = Domain.all,
    trapi_version: Annotated[
        str | None,
        typer.Option(
            "--trapi-version",
            "--tv",
            help="Scope version-split domains to one TRAPI version; "
            "omit to show them for both 1.6 and 2.0.",
        ),
    ] = None,
    files: Annotated[
        bool,
        typer.Option(
            "--files",
            "-f",
            help="Include the per-file query detail table (queries domain).",
        ),
    ] = False,
    raw: Annotated[
        bool,
        typer.Option(
            "--raw",
            "-r",
            help="Emit the full JSON surface to stdout instead of the rich view.",
        ),
    ] = False,
) -> None:
    """Show the runtime-resolved capability surface (rich to stderr, JSON on --raw/pipe)."""
    if trapi_version is not None and trapi_version not in ("1.6", "2.0"):
        console.print(
            f"[red]--trapi-version must be '1.6' or '2.0', got {trapi_version!r}.[/]"
        )
        raise typer.Exit(1)

    result = build_manifest(domain.value, trapi_version)

    # Piped stdout has no human to read the rich view, so it gets the JSON surface too.
    as_json = raw or not sys.stdout.isatty()
    if files and as_json:
        console.print(
            "Note: --files only affects the rich view; the JSON surface always includes "
            "per-file detail.",
            style="yellow",
        )
    if as_json:
        print(json.dumps(result))
    else:
        render_manifest(result, files=files)
