from contextlib import redirect_stdout
from pathlib import Path
from sys import stderr
from typing import Annotated, cast

import typer
from InquirerPy import inquirer
from rich.console import Console

from trapi_testing_tools.types import LogLevel, TestType
from trapi_testing_tools.utils import ENVIRONMENT_MAPPING, select_tests

console = Console(stderr=True)

app = typer.Typer(
    no_args_is_help=True,
    context_settings=dict(help_option_names=["-h", "--help"]),
)


@app.command("harness | h")
def harness(
    name: Annotated[list[str] | None, typer.Argument(help="")] = None,
    environment: Annotated[
        str | None,
        typer.Option(
            "--environment",
            "--env",
            "-e",
            help="Set the environment to use (e.g. bte.prod).",
        ),
    ] = None,
    log_level: LogLevel = typer.Option(  # Have to define differently due to fun Typer problems
        "WARNING",
        "--log-level",
        "-l",
        help="Level of logs to print.",
        case_sensitive=False,
    ),
    test_type: TestType | None = typer.Option(
        None,
        "--test-type",
        "--type",
        "-t",
        help="Type of test to run. A case is a collection of assets; A suite is a collection of cases. ",
    ),
    out: Annotated[
        Path | None,
        typer.Option(
            "--out",
            "-o",
            help="Path to save the report to. Additional files will save to this path with a suffix.",
        ),
    ] = None,
):
    # cache_tests()
    used_interactive = False  # TODO: output hint if interactive mode used
    if environment is None:
        with redirect_stdout(stderr):
            environment = inquirer.fuzzy(
                message="Select environment...",
                choices=[key for key in ENVIRONMENT_MAPPING.keys() if "." in key],
                instruction="(Type to filter, Tab to select, Enter to confirm)",
                border=True,
            ).execute()
        used_interactive = True

    if environment not in ENVIRONMENT_MAPPING.keys():
        console.print(
            f"Environment must be one of {(', '.join(ENVIRONMENT_MAPPING.keys()))}"
        )
        typer.Exit(1)

    if name is not None and test_type is None:
        test_type = TestType.suite

    if test_type is None:
        test_type = TestType[
            inquirer.fuzzy(
                message="Select test type...",
                choices=[e.value for e in TestType],
                border=True,
                instruction="(Type to filter, Tab to select, Enter to confirm)",
                info=True,
            ).execute()
        ]

    tests: list[Path] = []
    if name is None:
        try:
            tests = select_tests(cast(TestType, test_type).value)
        except Exception:
            console.print_exception(show_locals=True)
            console.print(
                "An error occurred while selecting tests. Please see the above traceback for more information."
            )

    tests = tests if name is None else [Path(path) for path in name]
    print(tests)  # TODO remove

    if used_interactive:
        # TODO print out a command hint to re-do this exact setup
        pass

    # TODO: run through tests
    # AKA integrate the harness code
