import re
import sys
from re import Pattern
from typing import override

import typer
from click import Context
from click.core import Command
from rich.console import Console
from typer.core import TyperGroup

from trapi_testing_tools.commands.analyze import app as analyze_app
from trapi_testing_tools.commands.curl import app as curl_app
from trapi_testing_tools.commands.harness import app as harness_app
from trapi_testing_tools.commands.ping import app as ping_app
from trapi_testing_tools.commands.pk import app as pk_app
from trapi_testing_tools.commands.test import app as test_app
from trapi_testing_tools.commands.validate import app as validate_app

console = Console(stderr=True)


class AliasGroup(TyperGroup):
    """Special AliasGroup that allows typer commands to have aliases."""

    _CMD_SPLIT_P: Pattern[str] = re.compile(r" ?[,|] ?")

    @override
    def get_command(self, ctx: Context, cmd_name: str) -> Command | None:
        """Get a command given the name."""
        cmd_name = self._group_cmd_name(default_name=cmd_name)
        return super().get_command(ctx, cmd_name)

    def _group_cmd_name(self, default_name: str) -> str:
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

app.add_typer(test_app)
app.add_typer(analyze_app)
app.add_typer(validate_app)
app.add_typer(ping_app)
app.add_typer(harness_app)
app.add_typer(pk_app)
app.add_typer(curl_app)
# TODO: make a command that curl-izes a given query


def main() -> None:
    """Run the Typer App."""
    app()


def test_shortcut() -> None:
    """Very hacky shortcut to directly use the `test` command from a project script."""
    sys.argv.insert(1, "test")
    app()



if __name__ == "__main__":
    main()
