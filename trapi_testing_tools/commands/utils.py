from contextlib import redirect_stdout
from pathlib import Path
from sys import stderr
from typing import Literal, overload

import typer
from InquirerPy import inquirer
from rich.console import Console

import queries as query_list
from trapi_testing_tools.types import OutputModes
from trapi_testing_tools.utils import ENVIRONMENT_MAPPING

console = Console(stderr=True)


@overload
def set_queries(
    queries: list[Path] | None, multi: Literal[True]
) -> tuple[list[Path], bool]: ...


@overload
def set_queries(
    queries: list[Path] | None, multi: Literal[False]
) -> tuple[Path, bool]: ...


@overload
def set_queries(queries: list[Path] | None) -> tuple[list[Path], bool]: ...


def set_queries(
    queries: list[Path] | None, multi: bool = True
) -> tuple[list[Path], bool] | tuple[Path, bool]:
    """Given the command arguments, ensure queries are selected."""
    used_interactive = False
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
                multiselect=multi,
                border=True,
                instruction="(Type to filter, Tab to select, Enter to confirm)",
                info=True,
            ).execute()
        if len(selection) == 0:
            raise typer.Abort()

        queries = [
            Path("./queries").joinpath(f"{path_str}.py").resolve()
            for path_str in (selection if type(selection) is list else [selection])
        ]
        used_interactive = True

    if (type(queries) is list) and not multi:
        return queries[0], used_interactive
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
