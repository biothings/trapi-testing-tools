import importlib
from collections.abc import Callable
from pathlib import Path
from typing import Annotated, cast

import typer
from rich.console import Console

import trapi_testing_tools
from trapi_testing_tools.commands.utils import set_environment, set_queries
from trapi_testing_tools.metakg import (
    EdgeSpec,
    Support,
    edge_supported,
    extract_edges,
    fetch_metakg,
    parse_metakg,
    parse_qualifier_flags,
    render_support,
)
from trapi_testing_tools.trapi_models import SUPPORTED_VERSIONS, TrapiVersion
from trapi_testing_tools.utils import (
    ENVIRONMENT_MAPPING,
    maybe_print_traceback,
    parse_query,
)

console = Console(stderr=True)
app = typer.Typer(
    no_args_is_help=False,
    context_settings=dict(help_option_names=["-h", "--help"]),
)


def _fetch[T](action: Callable[[], T], subject: str) -> T:
    """Run a fetch/parse, turning any failure into a friendly error and exit."""
    try:
        return action()
    except Exception as error:
        console.print(f"[red]ERROR: {subject} failed: {error!r}[/]")
        maybe_print_traceback()
        raise typer.Exit(1) from error


def _file_specs(
    queries: list[Path] | None, override_version: TrapiVersion | None
) -> dict[TrapiVersion, list[EdgeSpec]]:
    """Import each query file and collect its edges as specs, grouped by TRAPI version."""
    paths, _ = set_queries(queries, multi=True)

    by_version: dict[TrapiVersion, list[EdgeSpec]] = {}
    for path in paths:
        file = path.resolve().relative_to(Path(trapi_testing_tools.__path__[0]).parent)
        try:
            module = importlib.import_module(".".join(file.with_suffix("").parts))
            parsed = parse_query(module)
        except Exception as error:
            console.print(f"[red]ERROR: could not load {file}: {error!r}[/]")
            maybe_print_traceback()
            continue

        source = ".".join(file.with_suffix("").parts).removeprefix("queries.")
        for query in parsed:
            body = query.body
            query_graph = (
                body.get("message", {}).get("query_graph")
                if isinstance(body, dict)
                else None
            )
            if not isinstance(query_graph, dict):
                continue
            version = override_version or query.trapi_version
            by_version.setdefault(version, []).extend(
                extract_edges(query_graph, version, source)
            )

    return by_version


@app.command(
    "metakg | m",
    help="Check whether an environment's /meta_knowledge_graph supports an edge "
    "(-s/-p/-o/-q/-a) or every edge in one or more query files.",
)
def metakg(  # noqa: PLR0913
    queries: Annotated[
        list[Path] | None,
        typer.Argument(
            help="Query file(s) to check. Omit (with no -s/-p/-o) to "
            "pick interactively. Mutually exclusive with -s/-p/-o."
        ),
    ] = None,
    subject: Annotated[
        str | None,
        typer.Option("--subject", "-s", help="Subject category (Biolink), e.g. Gene."),
    ] = None,
    predicate: Annotated[
        str | None,
        typer.Option("--predicate", "-p", help="Predicate (Biolink), e.g. affects."),
    ] = None,
    obj: Annotated[
        str | None,
        typer.Option("--object", "-o", help="Object category (Biolink), e.g. Disease."),
    ] = None,
    qualifiers: Annotated[
        list[str] | None,
        typer.Option(
            "--qualifier",
            "-q",
            help="Qualifier as TYPE:VALUE (edge mode), repeatable, "
            "e.g. object_aspect_qualifier:expression.",
        ),
    ] = None,
    attributes: Annotated[
        list[str] | None,
        typer.Option(
            "--attribute",
            "-a",
            help="Attribute type CURIE the edge must offer (edge mode), repeatable.",
        ),
    ] = None,
    environment: Annotated[
        str | None,
        typer.Option(
            "--environment", "--env", "-e", help="Target environment (app.level)."
        ),
    ] = None,
    trapi_version: Annotated[
        str | None,
        typer.Option(
            "--trapi-version",
            help="TRAPI version (1.6 or 2.0); defaults per query file, else 1.6.",
        ),
    ] = None,
    raw: Annotated[
        bool,
        typer.Option("--raw", "-r", help="Print results as JSON to stdout."),
    ] = False,
) -> None:
    """Check metakg support for a flag-specified edge or a query file's edges."""
    using_flags = subject is not None or predicate is not None or obj is not None
    if using_flags and queries:
        console.print("[red]Provide either -s/-p/-o or a query file, not both.[/]")
        raise typer.Exit(1)
    if using_flags and not (subject and predicate and obj):
        console.print("[red]Edge mode needs all of -s, -p, and -o.[/]")
        raise typer.Exit(1)
    if (qualifiers or attributes) and not using_flags:
        console.print("[red]-q/-a are only valid with an -s/-p/-o edge.[/]")
        raise typer.Exit(1)

    if trapi_version is not None and trapi_version not in SUPPORTED_VERSIONS:
        console.print(
            f"[red]--trapi-version must be one of {', '.join(SUPPORTED_VERSIONS)}.[/]"
        )
        raise typer.Exit(1)
    version = trapi_version

    env_list, _ = set_environment([environment] if environment else None, multi=False)
    env = env_list[0]
    base_url = ENVIRONMENT_MAPPING[env]

    if using_flags:
        edge_version: TrapiVersion = version or "1.6"
        quals = _fetch(
            lambda: parse_qualifier_flags(qualifiers or [], edge_version),
            "parsing qualifiers",
        )
        spec = EdgeSpec(
            subjects=[cast(str, subject)],
            predicates=[cast(str, predicate)],
            objects=[cast(str, obj)],
            qualifier_constraints=quals,
            attribute_types=attributes or [],
        )
        specs_by_version = {edge_version: [spec]}
    else:
        specs_by_version = _file_specs(queries, version)

    if not any(specs_by_version.values()):
        console.print("[yellow]No edges to check.[/]")
        raise typer.Exit(1)

    response = _fetch(lambda: fetch_metakg(base_url), "fetching meta_knowledge_graph")

    results: list[Support] = []
    for spec_version, specs in specs_by_version.items():
        metakg_graph = _fetch(
            lambda v=spec_version: parse_metakg(response, v),
            "parsing meta_knowledge_graph",
        )
        results.extend(edge_supported(spec, metakg_graph.edges) for spec in specs)

    render_support(results, env, raw=raw)

    if any(not support.supported for support in results):
        raise typer.Exit(1)
