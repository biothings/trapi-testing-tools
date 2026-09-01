from contextlib import redirect_stdout
from sys import stderr
from typing import Annotated

import typer
from InquirerPy.prompts.fuzzy import FuzzyPrompt
from natsort import natsorted
from rich.console import Console

from trapi_testing_tools.config import CONFIG
from trapi_testing_tools.utils import check_apps_responsive, is_interactive

console = Console(stderr=True)
app = typer.Typer(
    no_args_is_help=False,
    context_settings=dict(help_option_names=["-h", "--help"]),
)


def _select_apps() -> list[str]:
    """Interactively multi-select which configured apps to ping."""
    with redirect_stdout(stderr):
        return FuzzyPrompt(
            message="Select app(s) to ping...",
            choices=natsorted(CONFIG.environments),
            multiselect=True,
            border=True,
            instruction="(Type to filter, Tab to select, Enter to confirm)",
            info=True,
        ).execute()


@app.command(
    "ping | p", help="Quickly check if servers are responsive by getting their metakg."
)
def ping(
    apps: Annotated[
        list[str] | None,
        typer.Argument(
            help="Which app(s) to check (all instances will be checked). "
            "Omit to select interactively."
        ),
    ] = None,
    check_all: Annotated[
        bool, typer.Option("--all", "-a", help="Check all instances of all apps.")
    ] = False,
) -> None:
    """Ping the given servers."""
    if check_all:
        check_apps_responsive(list(CONFIG.environments.items()))
        return

    selected = apps or (
        _select_apps() if is_interactive() else [CONFIG.default_environment]
    )
    if not selected:
        raise typer.Exit(0)

    resolved: list[tuple[str, dict[str, str]]] = []
    for raw_name in selected:
        name = CONFIG.default_environment if raw_name == "default" else raw_name
        if name not in CONFIG.environments:
            valid_apps = ", ".join(key for key in CONFIG.environments)
            console.print(f"App must be one of configured apps: {valid_apps}")
            raise typer.Exit(1)
        resolved.append((name, CONFIG.environments[name]))

    check_apps_responsive(resolved)
