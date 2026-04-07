import importlib
import json
from contextlib import redirect_stdout
from pathlib import Path
from sys import stderr
from types import ModuleType
from typing import Annotated

import typer
from InquirerPy import inquirer
from rich.console import Console

import trapi_testing_tools
from trapi_testing_tools.commands.utils import set_environment, set_queries
from trapi_testing_tools.utils import ENVIRONMENT_MAPPING, parse_query

console = Console(stderr=True)
app = typer.Typer(
    no_args_is_help=True,
    context_settings=dict(help_option_names=["-h", "--help"]),
)


@app.command("curl | c", help="Get a query in curl format.")
def curl(
    query: Annotated[
        Path | None, typer.Argument(help="Query file of interest.")
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
) -> None:
    """Get a query in curl format."""
    query, _ = set_queries([query] if query else None, multi=False)
    environment, _ = set_environment(environment)

    query = query.resolve().relative_to(Path(trapi_testing_tools.__path__[0]).parent)

    query_module = check_file(query)

    queries = parse_query(query_module)

    if (
        len(queries) > 1
        and not inquirer.confirm(
            "Query file defines multiple steps, print all (Will print first otherwise)?",
            default=True,
        ).execute()
    ):
        queries = queries[0:1]

    for step in queries:
        url = f"{ENVIRONMENT_MAPPING[environment]}{step.endpoint}"
        params = "&".join(
            [
                f"{name}={value}"
                for name, value in step.params.items()
            ]
        )
        if len(params) > 0:
            url += f"?{params}"

        headers = [
            f"{name}: {value}"
            for name, value in step.headers.items()
        ]

        command = [
            f"curl -X {step.method}",
            url,
            "-H 'Content-Type: application/json'",
            *headers,
        ]

        body = step.body
        if body:
            command.append(f"--data '{json.dumps(body, indent=2)}'")

        console.print(" \\\n".join(command))


def check_file(file: Path) -> ModuleType:
    """Check that a query file exists and can be used, returning it if so."""
    if file.suffix != ".py":
        console.print(
            f"ERROR: {file} is not a python file",
            style="red",
        )
        raise typer.Exit()
    if not file.exists():
        console.print(f"ERROR: {file} does not exist.", style="red")
        raise typer.Exit()
    try:
        import_path = ".".join(file.with_suffix("").parts)
        query = importlib.import_module(import_path)
        return query
    except Exception as error:
        console.print(f"ERROR: failed to read query file due to {error!r}.")
        with redirect_stdout(stderr):
            if inquirer.confirm(
                "Print traceback for this error?", default=False
            ).execute():
                console.print_exception(show_locals=True)
        raise typer.Exit() from error
