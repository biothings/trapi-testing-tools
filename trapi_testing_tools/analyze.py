import json
import sys
from contextlib import redirect_stdout
from pathlib import Path
from sys import stderr
from typing import Any

import typer
from InquirerPy.prompts.confirm import ConfirmPrompt
from rich.console import Console
from rich.text import Text

from analysis.base_analysis import AnalysisClass, ParametrizedAnalysis
from trapi_testing_tools.trapi_models import TrapiVersion, detect_version, models
from trapi_testing_tools.types import OutputModes
from trapi_testing_tools.utils import IndentedBlock, handle_output, serialize_body

console = Console(stderr=True)


def read_response_bytes(file: Path | None) -> tuple[bytes, str]:
    """Read raw response bytes from a file or stdin, returning them with a source label."""
    source = "stdin" if file is None else str(file)
    try:
        data = file.read_bytes() if file is not None else sys.stdin.buffer.read()
    except OSError as error:
        console.print(f"ERROR: could not read {source}: {error!r}", style="red")
        raise typer.Exit(1) from error

    if not data.strip():
        console.print(f"ERROR: no input read from {source}.", style="red")
        raise typer.Exit(1)

    return data, source


def parse_response(
    data: bytes, source: str, version: TrapiVersion | None = None
) -> Any:
    """Parse raw bytes into a TRAPI Response for the given (or active) TRAPI version."""
    try:
        return models(version).Response.from_json(data)
    except Exception as error:
        console.print(
            f"ERROR: {source} is not a valid TRAPI response: {error!r}", style="red"
        )
        raise typer.Exit(1) from error


def detect_response_version(data: bytes) -> TrapiVersion | None:
    """The supported TRAPI version a raw response's `schema_version` denotes, if determinable."""
    try:
        schema_version = json.loads(data).get("schema_version")
    except (ValueError, AttributeError):
        return None
    return detect_version(schema_version)


def load_response(file: Path | None, version: TrapiVersion | None = None) -> Any:
    """Load a TRAPI Response (for the given or active TRAPI version), from a file or stdin."""
    data, source = read_response_bytes(file)
    return parse_response(data, source, version)


def run_analyses(
    response: Any,
    analyses: list[AnalysisClass],
    forwarded_args: list[str],
    output_modes: OutputModes,
    save_path: Path | None = None,
) -> None:
    """Run each selected analysis sequentially against the response."""
    multiple = len(analyses) > 1
    for analysis in analyses:
        path = save_path
        if path is not None and multiple:
            path = path.with_name(f"{analysis.__name__}_{path.name}")
        manage_analysis(analysis, response, forwarded_args, output_modes, path)


def manage_analysis(
    analysis: AnalysisClass,
    response: Any,
    forwarded_args: list[str],
    output_modes: OutputModes,
    save_path: Path | None,
) -> None:
    """Run a single analysis and handle its output."""
    view_mode, save_mode = output_modes

    console.rule(Text("┌ ", style="rule.line") + analysis.__name__, align="left")
    console.push_render_hook(IndentedBlock())

    try:
        if issubclass(analysis, ParametrizedAnalysis):
            output = analysis.run(response, forwarded_args)
        else:
            output = analysis.analyze(response)
    except Exception as error:
        console.pop_render_hook()
        console.print(f"└ [red]Error:[/] {error!r}", style="rule.line", markup=True)
        with redirect_stdout(stderr):
            if ConfirmPrompt(
                "Print traceback for this error?", default=False
            ).execute():
                console.print_exception(show_locals=True)
        return

    handle_output(
        serialize_body(output), view_mode, save_mode, save_path, subject="analysis"
    )

    console.pop_render_hook()
    console.print("└ [green]✓ Done[/]", style="rule.line", markup=True)
