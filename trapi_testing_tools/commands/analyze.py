import typer

app = typer.Typer(
    no_args_is_help=True,
    context_settings=dict(help_option_names=["-h", "--help"]),
)


@app.command("analyze | a", help="Perform some analysis on a response.")
def analyze(a: str) -> None:
    """Run a given analysis on a response."""
    pass
