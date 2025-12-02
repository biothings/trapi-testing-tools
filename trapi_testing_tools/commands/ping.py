from typing import Annotated

import typer
from rich.console import Console

from trapi_testing_tools.utils import check_apps_responsive, config

console = Console(stderr=True)
app = typer.Typer(
    no_args_is_help=True,
    context_settings=dict(help_option_names=["-h", "--help"]),
)


@app.command(
    "ping | p", help="Quickly check if servers are responsive by getting their metakg."
)
def ping(
    app: Annotated[
        str,
        typer.Argument(help="Which app to check (all instances will be checked)."),
    ] = config["environments"]["default"],
    check_all: Annotated[
        bool, typer.Option("--all", "-a", help="Check all instances of all apps.")
    ] = False,
) -> None:
    """Ping the given servers."""
    if app not in config["environments"]:
        valid_apps = ", ".join(key for key in config["environments"])
        console.print(f"App must be one of configured apps: {valid_apps}")
        raise typer.Exit(1)

    if app == "default":
        app = config["environments"]["default"]

    apps: list[tuple[str, dict[str, str]]] = [(app, config["environments"][app])]
    if check_all:
        apps = list(config["environments"].items())

    check_apps_responsive(apps)
