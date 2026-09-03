import json
import sys
from contextlib import redirect_stdout
from pathlib import Path
from sys import stderr
from typing import Annotated, Any

import typer
from InquirerPy.prompts.confirm import ConfirmPrompt
from InquirerPy.prompts.fuzzy import FuzzyPrompt
from rich.console import Console

from analysis.base_analysis import AnalysisClass, ParametrizedAnalysis
from trapi_testing_tools.analyze import (
    collect_info,
    detect_response_version,
    parse_response,
    read_response_bytes,
    render_summary,
    render_verdict,
    run_analyses_inline,
    run_info_battery,
)
from trapi_testing_tools.commands.utils import (
    discover_analyses,
    set_analyses,
    set_output_modes,
)
from trapi_testing_tools.trapi_models import (
    DEFAULT_TRAPI_VERSION,
    SUPPORTED_VERSIONS,
    TrapiVersion,
    use_version,
)
from trapi_testing_tools.utils import handle_output, is_interactive, serialize_body

console = Console(stderr=True)
stdout_console = Console()

# Dir searched for interactive response selection (mirrors diff's picker).
RESPONSES_DIR = Path("responses")

app = typer.Typer(
    no_args_is_help=False,
    context_settings=dict(help_option_names=["-h", "--help"]),
)


def select_response() -> Path | None:
    """Interactively pick a response from ``responses/``; None if there's nothing to pick."""
    if not RESPONSES_DIR.is_dir():
        return None
    choices = sorted(
        str(path.relative_to(RESPONSES_DIR)) for path in RESPONSES_DIR.rglob("*.json")
    )
    if not choices:
        return None
    with redirect_stdout(stderr):
        pick = FuzzyPrompt(
            message="Select a response...",
            choices=choices,
            instruction="(Type to filter, Enter to confirm)",
            border=True,
        ).execute()
    return RESPONSES_DIR / pick if pick else None


def resolve_version(flag: str | None, data: bytes) -> TrapiVersion:
    """The TRAPI version: explicit flag, else the response's schema_version, else default."""
    if flag is not None:
        if flag not in SUPPORTED_VERSIONS:
            console.print(
                f"ERROR: unsupported --trapi-version {flag!r} "
                f"(choose from {', '.join(SUPPORTED_VERSIONS)}).",
                style="red",
            )
            raise typer.Exit(1)
        return flag
    return detect_response_version(data) or DEFAULT_TRAPI_VERSION


def _list_analyses(version: str) -> None:
    """Print available analyses (name + description) to stdout and exit."""
    available = discover_analyses(version)
    if not available:
        stdout_console.print("No analyses discovered.")
        raise typer.Exit()
    width = max(len(name) for name in available)
    for name in sorted(available):
        desc = (available[name].__doc__ or "").strip().removesuffix(".")
        stdout_console.print(f"[bold cyan]{name:<{width}}[/]  {desc}", highlight=False)
    raise typer.Exit()


def _show_analysis_help(names: list[str], forwarded_args: list[str], version: str) -> None:
    """Show a named analysis' own argument help without reading a response, then exit."""
    for cls in set_analyses(names, version)[0]:
        if issubclass(cls, ParametrizedAnalysis):
            cls.app(
                args=forwarded_args,
                prog_name=f"tt analyze {cls.__name__}",
                standalone_mode=False,
            )
        else:
            console.print(f"{cls.__name__} takes no arguments.")
    raise typer.Exit()


def _build_envelope(  # noqa: PLR0913
    model: Any,
    info_data: dict[str, Any],
    battery: list[dict[str, Any]],
    source: str,
    names: list[str] | None,
    version: TrapiVersion,
    forwarded_args: list[str],
) -> dict[str, Any]:
    """The single JSON envelope for `--pipe`: metadata + battery + any named analyses."""
    selected = set_analyses(names, version)[0] if names else []
    analyses_out = dict[str, Any]()
    for cls in selected:
        try:
            if issubclass(cls, ParametrizedAnalysis):
                output = cls.run(model, forwarded_args)
            else:
                output = cls.analyze(model)
        except Exception as error:
            analyses_out[cls.__name__] = {"error": repr(error)}
            continue
        analyses_out[cls.__name__] = serialize_body(output)
    return {
        "source": source,
        **info_data,
        "battery": battery,
        "analyses": analyses_out,
    }


def _select_analyses(names: list[str] | None, version: TrapiVersion) -> list[AnalysisClass]:
    """Resolve analyses to run after the summary: named, else an interactive confirm+picker."""
    if names:
        return set_analyses(names, version)[0]
    if is_interactive():
        with redirect_stdout(stderr):
            run_them = ConfirmPrompt(
                "Run analyses on this response?", default=False
            ).execute()
        if run_them:
            return set_analyses(None, version)[0]
    return []


@app.command(
    "analyze | a",
    help="Summarize a TRAPI response: metadata, metrics, standard battery, then analyses.",
    context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
)
def analyze(  # noqa: PLR0913
    file: Annotated[
        Path | None,
        typer.Argument(
            # No exists= validator: a `-- --help` tail binds here and must reach the passthrough.
            help="TRAPI response file (reads stdin if omitted; picked from responses/ when interactive).",
        ),
    ] = None,
    analysis: Annotated[
        list[str] | None,
        typer.Option(
            "--analysis",
            "-a",
            help="Analyses to run non-interactively (repeatable). Args after `--` are forwarded.",
        ),
    ] = None,
    list_analyses: Annotated[
        bool,
        typer.Option("--list", "-l", help="List available analyses and exit."),
    ] = False,
    no_analysis: Annotated[
        bool,
        typer.Option(
            "--no-analysis",
            "-A",
            help="Skip analyses entirely; just show metadata, metrics, and the battery.",
        ),
    ] = False,
    trapi_version: Annotated[
        str | None,
        typer.Option(
            "--trapi-version",
            help="TRAPI version to parse as (default: the response's schema_version, else 1.6).",
        ),
    ] = None,
    view: Annotated[
        bool | None,
        typer.Option(
            "--view/--no-view",
            "-v/-V",
            help="View analysis output (and offer to view the response body).",
            show_default="Prompt",
        ),
    ] = None,
    save: Annotated[
        Path | None,
        typer.Option(
            "--save",
            "-s",
            help="Write analysis output to path (prefixed with analysis name for multiple).",
        ),
    ] = None,
    no_save: Annotated[
        bool,
        typer.Option(
            "--no-save", "-S", help="Don't save analysis output and skip prompts to do so."
        ),
    ] = False,
    pipe: Annotated[
        bool,
        typer.Option(
            "--pipe",
            "-p",
            help="Emit one JSON envelope (metadata + battery + analyses) to stdout.",
        ),
    ] = False,
) -> None:
    """Summarize a captured TRAPI response (from a file or piped stdin), then run analyses.

    Prints metadata and metrics plus the standard test battery (minus HTTP status), runs
    any analyses (viewing/saving their output), then offers to view the response body
    (never saved). Exits nonzero if any battery check fails. Arguments after a `--`
    separator are forwarded to a parametrized analysis
    (e.g. `tt analyze r.json -a PathCount -- --start <C> --end <C>`).
    """
    if analysis and no_analysis:
        console.print("ERROR: --analysis/-a and --no-analysis/-A are mutually exclusive.", style="red")
        raise typer.Exit(1)

    if list_analyses:
        _list_analyses(trapi_version or DEFAULT_TRAPI_VERSION)

    # Everything after a literal `--` is forwarded verbatim to parametrized analyses.
    forwarded_args = list[str]()
    if "--" in sys.argv:
        forwarded_args = sys.argv[sys.argv.index("--") + 1 :]

    # click binds the first post-`--` token to `file`; undo so piped/picker input still works.
    if forwarded_args and file is not None and str(file) == forwarded_args[0]:
        file = None

    if analysis and any(arg in ("--help", "-h") for arg in forwarded_args):
        _show_analysis_help(analysis, forwarded_args, trapi_version or DEFAULT_TRAPI_VERSION)

    if file is None and is_interactive():
        file = select_response()
    data, source = read_response_bytes(file)
    version = resolve_version(trapi_version, data)

    with use_version(version):
        model = parse_response(data, source, version)
        info_data = collect_info(model, version, data)
        battery = run_info_battery(model, version)
        battery_failed = any(not item["passed"] for item in battery)

        if pipe:
            names = None if no_analysis else analysis
            envelope = _build_envelope(
                model, info_data, battery, source, names, version, forwarded_args
            )
            print(json.dumps(envelope))
            raise typer.Exit(1 if battery_failed else 0)

        render_summary(console, info_data, battery, source)

        # Select analyses only after the summary is on screen, so it informs the choice.
        selected: list[AnalysisClass] = (
            [] if no_analysis else _select_analyses(analysis, version)
        )
        output_modes = set_output_modes(view, save, no_save, False, selected)
        run_analyses_inline(console, model, selected, forwarded_args, output_modes, save)

        view_mode, _ = output_modes
        handle_output(
            serialize_body(model), view_mode, "skip", None, subject="response"
        )

        render_verdict(console, battery)
        if battery_failed:
            raise typer.Exit(1)
