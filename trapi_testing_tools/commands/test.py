from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

import queries as query_list
from trapi_testing_tools.commands.utils import (
    set_environment,
    set_output_modes,
    set_queries,
)
from trapi_testing_tools.run_query import run_queries
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
            help="Stop to view/save failing queries.",
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

    if all_routine:
        queries = list(Path(query_list.__path__[0]).rglob("routine/**/*.py"))
    queries, used_interactive = set_queries(queries)
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
