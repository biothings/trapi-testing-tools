from contextlib import redirect_stdout
from pathlib import Path
import re
from sys import stderr
import sys
from typing import Annotated, Optional, assert_type

import typer
from InquirerPy import inquirer
from rich.console import Console

from trapi_testing_tools import queries as query_list
from trapi_testing_tools.retrieve_by_pk import get_response_from_pk
from trapi_testing_tools.run_query import run_queries
from trapi_testing_tools.utils import EnvironmentMapping
from typer.core import TyperGroup
from trapi_testing_tools.utils import (
    check_apps_responsive,
    config,
)

console = Console(stderr=True)


class AliasGroup(TyperGroup):
    _CMD_SPLIT_P = re.compile(r" ?[,|] ?")

    def get_command(self, ctx, cmd_name):
        cmd_name = self._group_cmd_name(cmd_name)
        return super().get_command(ctx, cmd_name)

    def _group_cmd_name(self, default_name):
        for cmd in self.commands.values():
            name = cmd.name
            if name and default_name in self._CMD_SPLIT_P.split(name):
                return name
        return default_name


app = typer.Typer(
    cls=AliasGroup,
    no_args_is_help=True,
    context_settings=dict(help_option_names=["-h", "--help"]),
    help="A collection of tools for testing and analyzing all things TRAPI.",
)

# TODO: --analyze to auto-pass to analysis (and/or support analysis in the test definition)
# TODO: --asset # to auto-retrieve a test asset and use it instead
# TODO: --validate to auto-pass to validation


@app.command("test | t", help="Run a query.")
def test(
    queries: Annotated[
        Optional[list[Path]], typer.Argument(help="One or more query files to run")
    ] = None,
    environment: Annotated[
        Optional[str],
        typer.Option(
            "--environment",
            "--env",
            "-e",
            help="Set the environment to use (e.g. bte.prod).",
        ),
    ] = None,
    all: Annotated[
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
        Optional[bool],
        typer.Option(
            "--view/--no-view",
            "-v/-V",
            help="View response body in jless after each file completes (normal/debug modes).",
            show_default="Prompt",
        ),
    ] = None,
    save: Annotated[
        Optional[Path],
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
):
    used_interactive = False

    if all:
        queries = list(Path(query_list.__path__[0]).rglob("routine/**/*.py"))
    if queries is None:
        valid_files = [
            str(
                path.relative_to(Path(query_list.__path__[0]).resolve()).with_suffix("")
            )
            for path in Path(query_list.__path__[0]).rglob("**/*.py")
        ]
        with redirect_stdout(stderr):
            selection = inquirer.fuzzy(
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
            Path("./trapi_testing_tools/queries").joinpath(f"{path_str}.py").resolve()
            for path_str in selection
        ]
        used_interactive = True

    if environment is None:
        with redirect_stdout(stderr):
            environment = inquirer.fuzzy(
                message="Select environment...",
                choices=[key for key in EnvironmentMapping.keys() if "." in key],
                instruction="(Type to filter, Tab to select, Enter to confirm)",
                border=True,
            ).execute()
        used_interactive = True

    if environment not in EnvironmentMapping.keys():
        console.print(
            f"Environment must be one of {(', '.join(EnvironmentMapping.keys()))}"
        )
        raise typer.Exit(1)

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

    if used_interactive:
        opts = [f"-e {environment}"]
        if all:
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
            f"\\[Hint] Re-run this command more quickly using: tt test {' '.join(opts)} {' '.join(str(q) for q in queries)}",
            style="italic bright_black",
            soft_wrap=True,
            highlight=False,
        )
        pass

    run_queries(
        queries,
        EnvironmentMapping[environment],
        view_mode,
        save_mode,
        save,
        debug,
    )


@app.command("analyze | a", help="Perform some analysis on a response.")
def analyze(a: str):
    pass


@app.command("validate | v")
def validate():
    pass


@app.command("harness | h")
def harness():
    pass


@app.command(
    help="Drill down into ARS PK to get a response of interest.", no_args_is_help=True
)
def pk(
    pk: Annotated[
        str, typer.Argument(help="The Primary Key of a given ARS query run.")
    ],
    ara: Annotated[
        Optional[str],
        typer.Option(
            "--ara", "-a", help="The ARA you wish to retrieve the response of."
        ),
    ] = None,
    view: Annotated[
        Optional[bool],
        typer.Option(
            "--view/--no-view",
            "-v/-V",
            help="View response body in jless after it's retrieved.",
            show_default="Prompt",
        ),
    ] = None,
    save: Annotated[
        Optional[Path],
        typer.Option(
            "--save",
            "-s",
            help="Write response to path.",
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
):
    view_mode = "prompt"
    save_mode = "prompt"
    if view is not None:
        view_mode = "every" if view else "skip"
    if save is not None:
        save_mode = "every"
    if no_save:
        save_mode = "skip"
    if pipe:
        view_mode = "pipe"
        save_mode = "skip"
    get_response_from_pk(
        pk,
        ara,
        view_mode,
        save_mode,
        save,
    )
    pass


@app.command(
    "ping | p", help="Quickly check if servers are responsive by getting their metakg."
)
def ping(
    app: Annotated[
        str,
        typer.Argument(help="Which app to check (all instances will be checked)."),
    ] = config["environments"]["default"],
    all: Annotated[
        bool, typer.Option("--all", "-a", help="Check all instances of all apps.")
    ] = False,
):
    if app not in config["environments"]:
        valid_apps = ", ".join(key for key in config["environments"])
        console.print(f"App must be one of configured apps: {valid_apps}")
        raise typer.Exit(1)

    if app == "default":
        app = config["environments"]["default"]

    apps: list[tuple[str, dict]] = [(app, config["environments"][app])]
    if all:
        apps = list(config["environments"].items())

    check_apps_responsive(apps)


def main():
    app()


def test_shortcut():
    """Very hacky shortcut to directly use the `test` command from a poetry script."""
    sys.argv.insert(1, "test")
    app()


if __name__ == "__main__":
    main()
