from contextlib import redirect_stdout
from pathlib import Path
from sys import stderr
from typing import Annotated

import typer
from InquirerPy.prompts.fuzzy import FuzzyPrompt
from rich.console import Console

from trapi_testing_tools.analyze import (
    detect_response_version,
    parse_response,
    read_response_bytes,
)
from trapi_testing_tools.commands.utils import set_output_modes
from trapi_testing_tools.diff import (
    build_report,
    colorize_report,
    diff_responses,
    render_report,
    render_text_report,
    render_verdict,
)
from trapi_testing_tools.trapi_models import (
    DEFAULT_TRAPI_VERSION,
    SUPPORTED_VERSIONS,
    TrapiVersion,
)
from trapi_testing_tools.utils import handle_output, is_interactive

console = Console(stderr=True)


def resolve_version(
    flag: str | None, left_data: bytes, right_data: bytes
) -> TrapiVersion:
    """Choose the TRAPI version: explicit flag, else the responses' schema_version, else default."""
    if flag is not None:
        if flag not in SUPPORTED_VERSIONS:
            console.print(
                f"ERROR: unsupported --trapi-version {flag!r} "
                f"(choose from {', '.join(SUPPORTED_VERSIONS)}).",
                style="red",
            )
            raise typer.Exit(1)
        return flag

    left_version = detect_response_version(left_data)
    right_version = detect_response_version(right_data)
    if left_version and right_version and left_version != right_version:
        console.print(
            f"WARNING: left is TRAPI {left_version} but right is {right_version}; "
            f"diffing both as {left_version}.",
            style="yellow",
        )
    return left_version or right_version or DEFAULT_TRAPI_VERSION


# Dir searched for interactive response selection (mirrors ./queries discovery).
RESPONSES_DIR = Path("responses")

app = typer.Typer(
    no_args_is_help=True,
    context_settings=dict(help_option_names=["-h", "--help"]),
)


def select_responses() -> tuple[Path, Path]:
    """Interactively pick a left/baseline and right/new response from ``responses/``."""
    choices = (
        sorted(
            str(path.relative_to(RESPONSES_DIR))
            for path in RESPONSES_DIR.rglob("*.json")
        )
        if RESPONSES_DIR.is_dir()
        else []
    )
    if not choices:
        console.print(
            f"No response files found under {RESPONSES_DIR}/ to diff.", style="red"
        )
        raise typer.Exit(1)
    with redirect_stdout(stderr):
        left = FuzzyPrompt(
            message="Select left/baseline response...",
            choices=choices,
            instruction="(Type to filter, Enter to confirm)",
            border=True,
        ).execute()
        right = FuzzyPrompt(
            message="Select right/new response...",
            choices=choices,
            instruction="(Type to filter, Enter to confirm)",
            border=True,
        ).execute()
    if not left or not right:
        raise typer.Abort()
    return RESPONSES_DIR / left, RESPONSES_DIR / right


@app.command(
    "diff | d", help="Diff two TRAPI responses (TRAPI-aware, order-insensitive)."
)
def diff(  # noqa: PLR0913
    left: Annotated[
        Path | None,
        typer.Argument(
            help="Left/baseline TRAPI response file. If both files are omitted, interactively picked from responses.",
            exists=True,
            dir_okay=False,
            readable=True,
        ),
    ] = None,
    right: Annotated[
        Path | None,
        typer.Argument(
            help="Right/new TRAPI response file (reads stdin if omitted).",
            exists=True,
            dir_okay=False,
            readable=True,
        ),
    ] = None,
    identity: Annotated[
        bool,
        typer.Option(
            "--identity",
            "-i",
            help="Identity mode: report only members added/removed by TRAPI .hash() "
            "identity. Default is a full structural diff.",
        ),
    ] = False,
    trapi_version: Annotated[
        str | None,
        typer.Option(
            "--trapi-version",
            help="TRAPI version to parse and diff as (default: the responses' "
            "schema_version, else 1.6). Both responses are diffed as one version.",
        ),
    ] = None,
    view: Annotated[
        bool | None,
        typer.Option(
            "--view/--no-view",
            "-v/-V",
            help="View the JSON report after diffing.",
            show_default="Prompt",
        ),
    ] = None,
    save: Annotated[
        Path | None,
        typer.Option("--save", "-s", help="Write the JSON report to a path."),
    ] = None,
    no_save: Annotated[
        bool,
        typer.Option(
            "--no-save", "-S", help="Don't save the report and skip prompts to do so."
        ),
    ] = False,
    full: Annotated[
        bool,
        typer.Option(
            "--full",
            "-f",
            help="Expand added/removed/changed content inline in the plaintext report "
            "(ignored with --json, which is always full).",
        ),
    ] = False,
    json_output: Annotated[
        bool,
        typer.Option(
            "--json",
            "-j",
            help="Emit the report as machine-readable JSON instead of plaintext.",
        ),
    ] = False,
    pipe: Annotated[
        bool,
        typer.Option("--pipe", "-p", help="Output the report to stdout for piping."),
    ] = False,
) -> None:
    """Diff two TRAPI responses.

    Both responses are normalized (edges re-keyed by hash, references remapped) so they
    compare regardless of each service's edge ids, and unordered collections are aligned
    by identity rather than position.

    With both file arguments omitted, an interactive terminal is prompted to pick the two
    responses from responses/; otherwise LEFT is required (RIGHT falls back to stdin).
    """
    strict = not identity
    if left is None:
        if not is_interactive():
            console.print(
                "ERROR: provide a LEFT response file (and RIGHT, or pipe one to stdin).",
                style="red",
            )
            raise typer.Exit(1)
        left, right = select_responses()

    left_name = str(left)
    right_name = str(right) if right is not None else "<stdin>"
    left_data, left_source = read_response_bytes(left)
    right_data, right_source = read_response_bytes(right)

    version = resolve_version(trapi_version, left_data, right_data)
    left_response = parse_response(left_data, left_source, version)
    right_response = parse_response(right_data, right_source, version)

    output_modes = set_output_modes(view, save, no_save, pipe, ["diff"])
    view_mode, save_mode = output_modes

    deltas = diff_responses(
        left_response, right_response, strict=strict, version=version
    )
    render_report(deltas, strict=strict)
    report = (
        build_report(deltas, strict=strict)
        if json_output
        else render_text_report(
            deltas,
            strict=strict,
            left_name=left_name,
            right_name=right_name,
            full=full,
        )
    )
    handle_output(
        report,
        view_mode,
        save_mode,
        save,
        subject="report",
        view_transform=None if json_output else colorize_report,
    )
    render_verdict(deltas)
