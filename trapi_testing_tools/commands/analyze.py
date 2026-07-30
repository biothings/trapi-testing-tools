import sys
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

from analysis.base_analysis import ParametrizedAnalysis
from trapi_testing_tools.analyze import load_response, run_analyses
from trapi_testing_tools.commands.utils import (
    discover_analyses,
    set_analyses,
    set_output_modes,
)

console = Console(stderr=True)
stdout_console = Console()
app = typer.Typer(
    no_args_is_help=True,
    context_settings=dict(help_option_names=["-h", "--help"]),
)


@app.command(
    "analyze | a",
    help="Run one or more analyses on a TRAPI response.",
    context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
)
def analyze(  # noqa: PLR0913
    analyses: Annotated[
        list[str] | None,
        typer.Argument(help="One or more analyses to run."),
    ] = None,
    list_analyses: Annotated[
        bool,
        typer.Option("--list", "-l", help="List available analyses and exit."),
    ] = False,
    file: Annotated[
        Path | None,
        typer.Option(
            "--file",
            "-f",
            help="Read the response from a file (instead of stdin).",
            exists=True,
            dir_okay=False,
            readable=True,
        ),
    ] = None,
    view: Annotated[
        bool | None,
        typer.Option(
            "--view/--no-view",
            "-v/-V",
            help="View analysis output after each analysis completes.",
            show_default="Prompt",
        ),
    ] = None,
    save: Annotated[
        Path | None,
        typer.Option(
            "--save",
            "-s",
            help="Write analysis output to path. Will prefix with analysis name for multiple files.",
        ),
    ] = None,
    no_save: Annotated[
        bool,
        typer.Option(
            "--no-save", "-S", help="Don't save output and skip prompts to do so."
        ),
    ] = False,
    pipe: Annotated[
        bool,
        typer.Option(
            "--pipe",
            "-p",
            help="Instead of viewing, output directly to stdout for piping.",
        ),
    ] = False,
) -> None:
    """Run one or more analyses on a TRAPI response (from a file or piped stdin).

    Arguments after a `--` separator are forwarded to any parametrized analysis
    (e.g. `tt analyze PathCount -- --start <CURIE> --end <CURIE>`).
    """
    if list_analyses:
        available = discover_analyses()
        if not available:
            stdout_console.print("No analyses discovered.")
            raise typer.Exit()
        width = max(len(name) for name in available)
        for name in sorted(available):
            desc = (available[name].__doc__ or "").strip().removesuffix(".")
            stdout_console.print(
                f"[bold cyan]{name:<{width}}[/]  {desc}", highlight=False
            )
        raise typer.Exit()

    # Everything after a literal `--` is forwarded verbatim to parametrized analyses.
    forwarded_args = list[str]()
    if "--" in sys.argv:
        forwarded_args = sys.argv[sys.argv.index("--") + 1 :]

    # The `analyses` positional also swallowed the forwarded tail; strip it back off.
    names = list(analyses or [])
    if forwarded_args:
        names = names[: len(names) - len(forwarded_args)]

    # Don't want interactive on pipe for complexity reasons
    if file is None and not names:
        console.print(
            "Interactive analysis selection not supported when piping input.",
            style="red",
        )
        raise typer.Exit(1)

    selected, _ = set_analyses(names or None)

    # Shortcut to show inner layer help without response checking
    if any(arg in ("--help", "-h") for arg in forwarded_args):
        for analysis in selected:
            if issubclass(analysis, ParametrizedAnalysis):
                analysis.app(
                    args=forwarded_args,
                    prog_name=f"tt analyze {analysis.__name__}",
                    standalone_mode=False,
                )
            else:
                console.print(f"{analysis.__name__} takes no arguments.")
        raise typer.Exit()

    output_modes = set_output_modes(view, save, no_save, pipe, selected)
    response = load_response(file)
    run_analyses(response, selected, forwarded_args, output_modes, save)
