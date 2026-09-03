import json
import re
from contextlib import suppress
from pathlib import Path
from types import ModuleType
from typing import Annotated, Any

import typer
from rich.console import Console

import queries
from tests.base_test import Test
from tests.battery import standard_battery, standard_battery_2_0
from trapi_testing_tools.callback import CallbackMode
from trapi_testing_tools.commands.norm import _resolve_service_url
from trapi_testing_tools.commands.utils import set_environment, set_output_modes
from trapi_testing_tools.normalize import resolve_names
from trapi_testing_tools.query_utils import one_hop
from trapi_testing_tools.report import PipeMode
from trapi_testing_tools.run_query import run_queries
from trapi_testing_tools.utils import ENVIRONMENT_MAPPING

# A `nameres:<name>` id value is resolved to a CURIE via Name Resolver (top hit).
NAMERES_PREFIX = "nameres:"
NAMERES_MATURITY = "test"

console = Console(stderr=True)
app = typer.Typer(
    no_args_is_help=True,
    context_settings=dict(help_option_names=["-h", "--help"]),
)


def _parse_pairs(items: list[str] | None, *, as_json: bool) -> dict[str, Any]:
    """Parse repeatable ``key=value`` options into a dict.

    With ``as_json`` each value is `json.loads`-ed, falling back to the raw string.
    """
    parsed: dict[str, Any] = {}
    for item in items or []:
        key, sep, value = item.partition("=")
        if not sep:
            console.print(f"Expected key=value, got {item!r}.", style="red")
            raise typer.Exit(1)
        if as_json:
            with suppress(json.JSONDecodeError):
                value = json.loads(value)
        parsed[key] = value
    return parsed


def _resolve_nameres(values: list[str] | None) -> list[str] | None:
    """Replace each ``nameres:<name>`` id value with its top Name Resolver CURIE."""
    if not values or not any(value.startswith(NAMERES_PREFIX) for value in values):
        return values

    base_url = _resolve_service_url("nameres", NAMERES_MATURITY)
    resolved: list[str] = []
    for value in values:
        if not value.startswith(NAMERES_PREFIX):
            resolved.append(value)
            continue

        name = value[len(NAMERES_PREFIX) :].strip()
        try:
            hits = resolve_names([name], base_url=base_url, limit=1, types=[], autocomplete=True)
        except Exception as error:
            console.print(f"Name Resolver lookup for {name!r} failed: {error!r}", style="red")
            raise typer.Exit(1) from error

        hit = hits[0] if isinstance(hits, list) and hits else None
        if not hit or not hit.get("curie"):
            console.print(f"No Name Resolver match for {name!r}.", style="red")
            raise typer.Exit(1)

        label = hit.get("label") or ""
        console.print(
            f"Resolved {name!r} → {hit['curie']}{f' ({label})' if label else ''}",
            style="bright_black",
        )
        resolved.append(hit["curie"])
    return resolved


def _slug(
    subject: list[str] | None, predicate: list[str] | None, obj: list[str] | None
) -> str:
    """A short filesystem-safe label for the inline query, from its endpoints."""
    parts = [part[0] for part in (subject, predicate, obj) if part] or ["query"]
    return re.sub(r"[^0-9A-Za-z]+", "-", "-".join(parts)).strip("-") or "query"


def _build_module(
    body: object,
    endpoint: str,
    tests: list[type[Test]] | None,
    trapi_version: str,
    slug: str,
) -> ModuleType:
    """Wrap an inline query into a module exposing the globals ``parse_query`` reads."""
    module = ModuleType("tt_inline_query")
    module.__dict__.update(
        __file__=str(Path(queries.__path__[0]) / "inline" / f"{slug}.py"),
        method="POST",
        endpoint=endpoint,
        body=body,
        tests=tests,
        trapi_version=trapi_version,
    )
    return module


@app.command("query | q", help="Build and run a one-hop query inline.")
def query(  # noqa: PLR0913
    subject_category: Annotated[
        list[str] | None,
        typer.Option("--subject-category", "--sc", help="Category CURIE(s) for the subject node."),
    ] = None,
    object_category: Annotated[
        list[str] | None,
        typer.Option("--object-category", "--oc", help="Category CURIE(s) for the object node."),
    ] = None,
    subject_ids: Annotated[
        list[str] | None,
        typer.Option(
            "--subject-ids",
            "--si",
            help="CURIE(s) pinning the subject node; a 'nameres:<name>' value resolves to its top Name Resolver CURIE.",
        ),
    ] = None,
    object_ids: Annotated[
        list[str] | None,
        typer.Option(
            "--object-ids",
            "--oi",
            help="CURIE(s) pinning the object node; a 'nameres:<name>' value resolves to its top Name Resolver CURIE.",
        ),
    ] = None,
    predicate: Annotated[
        list[str] | None,
        typer.Option("--predicate", "--pred", help="Predicate CURIE(s) for the edge."),
    ] = None,
    inferred: Annotated[
        bool,
        typer.Option("--inferred", help="Set the edge's knowledge_type to 'inferred'."),
    ] = False,
    qualifier: Annotated[
        list[str] | None,
        typer.Option(
            "--qualifier",
            "-q",
            help="Edge qualifier as type=value (repeatable), e.g. object_aspect_qualifier=activity.",
        ),
    ] = None,
    param: Annotated[
        list[str] | None,
        typer.Option(
            "--param",
            help="Top-level body field as key=value (repeatable); value is JSON-parsed, e.g. bypass_cache=true.",
        ),
    ] = None,
    is_async: Annotated[
        bool,
        typer.Option("--async", help="Send to /asyncquery instead of /query."),
    ] = False,
    trapi_version: Annotated[
        str,
        typer.Option("--trapi-version", "--tv", help="TRAPI version for response parsing and battery selection."),
    ] = "1.6",
    no_tests: Annotated[
        bool,
        typer.Option("--no-tests", help="Send the query without running the standard test battery."),
    ] = False,
    environment: Annotated[
        list[str] | None,
        typer.Option(
            "--environment",
            "--env",
            "-e",
            help="Environment(s) to run against (e.g. retriever.dev). Multiple environments run the query against each.",
        ),
    ] = None,
    debug: Annotated[
        bool,
        typer.Option("--debug", "-d", help="Only surface the response when the query fails."),
    ] = False,
    view: Annotated[
        bool | None,
        typer.Option(
            "--view/--no-view",
            "-v/-V",
            help="View response body in jless after the query completes.",
            show_default="Prompt",
        ),
    ] = None,
    save: Annotated[
        Path | None,
        typer.Option("--save", "-s", help="Write response to path."),
    ] = None,
    no_save: Annotated[
        bool,
        typer.Option("--no-save", "-S", help="Don't save response and skip prompts to do so."),
    ] = False,
    pipe: Annotated[
        PipeMode | None,
        typer.Option(
            "--pipe",
            "-p",
            help="Pipe JSON to stdout: 'plain' (response body, for tt analyze), "
            "'report' (run/test report, no bodies), or 'full' (report with bodies).",
        ),
    ] = None,
    callback_mode: Annotated[
        CallbackMode | None,
        typer.Option(
            "--callback-mode",
            "--cb",
            help="How async /asyncquery results are received: auto, tunnel, direct, or poll.",
        ),
    ] = None,
    against: Annotated[
        Path | None,
        typer.Option(
            "--against",
            "-a",
            help="Diff the response against this TRAPI response file (structural).",
        ),
    ] = None,
) -> None:
    """Build a one-hop query from flags and run it against one or more environments."""
    if not any((subject_category, object_category, subject_ids, object_ids)):
        console.print(
            "Specify at least one node constraint (--subject-ids/--object-ids or "
            "--subject-category/--object-category).",
            style="red",
        )
        raise typer.Exit(1)

    if trapi_version not in ("1.6", "2.0"):
        console.print(f"--trapi-version must be '1.6' or '2.0', got {trapi_version!r}.", style="red")
        raise typer.Exit(1)

    subject_ids = _resolve_nameres(subject_ids)
    object_ids = _resolve_nameres(object_ids)

    body = one_hop(
        subject_category,
        object_category,
        subject_ids=subject_ids,
        object_ids=object_ids,
        predicate=predicate,
        inferred=inferred,
        qualifiers=_parse_pairs(qualifier, as_json=False) or None,
        **_parse_pairs(param, as_json=True),
    )

    tests = (
        None
        if no_tests
        else (standard_battery_2_0() if trapi_version == "2.0" else standard_battery())
    )
    module = _build_module(
        body,
        "/asyncquery" if is_async else "/query",
        tests,
        trapi_version,
        _slug(subject_ids or subject_category, predicate, object_ids or object_category),
    )

    environment, _ = set_environment(environment)
    output_modes = set_output_modes(view, save, no_save, pipe is not None, [module], allow_multi=True)
    targets = [(env, ENVIRONMENT_MAPPING[env]) for env in environment]

    passed = run_queries(
        [module],
        targets,
        output_modes,
        save,
        debug,
        pipe,
        callback_mode=callback_mode,
        against=against,
    )

    if not passed:
        raise typer.Exit(1)
