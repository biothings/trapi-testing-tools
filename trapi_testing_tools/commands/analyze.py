import typer

app = typer.Typer(
    no_args_is_help=True,
    context_settings=dict(help_option_names=["-h", "--help"]),
)


@app.command("analyze | a")
def analyze(a: str) -> None:
    """Run a given analysis on a response."""
    # TODO take from pipe or from path arg (kwarg)
    pass
