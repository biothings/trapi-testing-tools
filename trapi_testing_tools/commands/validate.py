import typer

app = typer.Typer(
    no_args_is_help=True,
    context_settings=dict(help_option_names=["-h", "--help"]),
)


@app.command("validate | v")
def validate() -> None:
    """Validate the given TRAPI content."""
    pass
