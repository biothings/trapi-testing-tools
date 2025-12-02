from contextlib import redirect_stdout
from pathlib import Path
from sys import stderr
from typing import Annotated

import typer
from InquirerPy import inquirer
from rich.console import Console

import queries as query_list
from trapi_testing_tools.run_query import run_queries
from trapi_testing_tools.types import OutputModes
from trapi_testing_tools.utils import (
    ENVIRONMENT_MAPPING,
)

console = Console(stderr=True)
app = typer.Typer(
    no_args_is_help=True,
    context_settings=dict(help_option_names=["-h", "--help"]),
)

# TODO: --analyze to auto-pass to analysis (and/or support analysis in the test definition)
# TODO: --validate to auto-pass to validation


@app.command("test | t", help="Run a query.")
def test(  # noqa: PLR0913
    queries: Annotated[
        list[Path] | None, typer.Argument(help="One or more query files to run")
    ] = None,
    environment: Annotated[
        str | None,
        typer.Option(
            "--environment",
            "--env",
            "-e",
            help="Set the environment to use (e.g. bte.prod).",
        ),
    ] = None,
    all_routine: Annotated[
        bool,
        typer.Option(
            "--all", "-a", help="Select all routine files (overrides file arguments)."
        ),
    ] = False,
    debug: Annotated[
        bool,
        typer.Option(
            "--debug",
            "-d",
            help="Like --test, but stop to view/save failing queries.",
        ),
    ] = False,
    view: Annotated[
        bool | None,
        typer.Option(
            "--view/--no-view",
            "-v/-V",
            help="View response body in jless after each file completes (normal/debug modes).",
            show_default="Prompt",
        ),
    ] = None,
    save: Annotated[
        Path | None,
        typer.Option(
            "--save",
            "-s",
            help="Write response to path. Will prefix with query name for multiple files.",
        ),
    ] = None,
    no_save: Annotated[
        bool,
        typer.Option(
            "--no-save",
            "-S",
            help="Don't save response and skip prompts to do so.",
        ),
    ] = False,
    pipe: Annotated[
        bool,
        typer.Option(
            "--pipe",
            "-p",
            help="Instead of viewing, output response directly to stdout for piping",
        ),
    ] = False,
) -> None:
    """Run one or more queries against a specified environment."""
    # cache_tests()
    used_interactive = False

    queries, used_interactive = set_queries(all_routine, queries)
    environment, used_interactive = set_environment(environment)
    output_modes = set_output_modes(view, save, no_save, pipe, queries)

    # Ouptut hint to repeat quicker
    if used_interactive:
        opts = [f"-e {environment}"]
        if all_routine:
            opts.append("-a")
        if debug:
            opts.append("-d")
        if view is not None:
            opts.append("-v" if view else "-V")
        if save is not None:
            opts.append(f"-s {save}")
        if no_save:
            opts.append("-S")
        if pipe:
            opts.append("-p")
        console.print(
            f"\\[Hint] Re-run this command more quickly using: tt test {' '.join(opts)} {' '.join(str(q.relative_to(Path.cwd())) for q in queries)}",
            style="italic bright_black",
            soft_wrap=True,
            highlight=False,
        )

    run_queries(
        queries,
        ENVIRONMENT_MAPPING[environment],
        output_modes,
        save,
        debug,
    )


def set_queries(
    all_routine: bool, queries: list[Path] | None
) -> tuple[list[Path], bool]:
    """Given the command arguments, ensure queries are selected."""
    used_interactive = False
    if all_routine:
        queries = list(Path(query_list.__path__[0]).rglob("routine/**/*.py"))
    if queries is None:
        valid_files = [
            str(
                path.relative_to(Path(query_list.__path__[0]).resolve()).with_suffix("")
            )
            for path in Path(query_list.__path__[0]).rglob("**/*.py")
        ]
        with redirect_stdout(stderr):
            selection = inquirer.fuzzy(  # pyright:ignore[reportPrivateImportUsage]
                message="Select query file(s)...",
                choices=valid_files,
                multiselect=True,
                border=True,
                instruction="(Type to filter, Tab to select, Enter to confirm)",
                info=True,
            ).execute()
        if len(selection) == 0:
            raise typer.Abort()

        queries = [
            Path("./queries").joinpath(f"{path_str}.py").resolve()
            for path_str in selection
        ]
        used_interactive = True

    return queries, used_interactive


def set_environment(environment: str | None) -> tuple[str, bool]:
    """Ensure a proper target environment has been selected."""
    used_interactive = False
    if environment is None:
        with redirect_stdout(stderr):
            environment = inquirer.fuzzy(  # pyright:ignore[reportPrivateImportUsage]
                message="Select environment...",
                choices=[key for key in ENVIRONMENT_MAPPING if "." in key],
                instruction="(Type to filter, Tab to select, Enter to confirm)",
                border=True,
            ).execute()
        used_interactive = True

    if environment is None or environment not in ENVIRONMENT_MAPPING:
        console.print(
            f"Environment must be one of {(', '.join(ENVIRONMENT_MAPPING.keys()))}"
        )
        raise typer.Exit(1)

    return environment, used_interactive


def set_output_modes(
    view: bool | None,
    save: Path | None,
    no_save: bool,
    pipe: bool,
    queries: list[Path],
) -> OutputModes:
    """Set output modes based on given arguments."""
    view_mode = "prompt"
    save_mode = "prompt"
    if view is not None:
        view_mode = "every" if view else "skip"
    if save is not None:
        save_mode = "every"
    if no_save:
        save_mode = "skip"
    if pipe:
        if len(queries) > 1:
            console.print("Pipe mode only supported for single queries.")
            raise typer.Exit(1)
        view_mode = "pipe"
        save_mode = "skip"

    return view_mode, save_mode
