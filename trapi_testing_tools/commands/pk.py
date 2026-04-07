from pathlib import Path
from typing import Annotated

import typer

from trapi_testing_tools.retrieve_by_pk import get_response_from_pk

app = typer.Typer(
    no_args_is_help=True,
    context_settings=dict(help_option_names=["-h", "--help"]),
)


@app.command(no_args_is_help=True)
def pk(  # noqa:PLR0913
    pk: Annotated[
        str, typer.Argument(help="The Primary Key of a given ARS query run.")
    ],
    ara: Annotated[
        str | None,
        typer.Option(
            "--ara", "-a", help="The ARA you wish to retrieve the response of."
        ),
    ] = None,
    view: Annotated[
        bool | None,
        typer.Option(
            "--view/--no-view",
            "-v/-V",
            help="View response body in jless after it's retrieved.",
            show_default="Prompt",
        ),
    ] = None,
    save: Annotated[
        Path | None,
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
) -> None:
    """Drill down into ARS PK to get a response of interest."""
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
