import contextlib
import os
import signal
from contextlib import redirect_stdout
from enum import StrEnum
from sys import stderr
from typing import Annotated, Any

import typer
from InquirerPy.prompts.confirm import ConfirmPrompt
from rich.console import Console

from trapi_testing_tools.callback import (
    clear_tunnel_info,
    daemon_alive,
    read_tunnel_info,
    start_tunnel,
)
from trapi_testing_tools.utils import is_interactive

console = Console(stderr=True)
app = typer.Typer(
    no_args_is_help=False,
    context_settings=dict(help_option_names=["-h", "--help"]),
)


class _Action(StrEnum):
    start = "start"
    stop = "stop"


def _show_status(info: dict[str, Any] | None) -> bool:
    """Print the tunnel's status; return whether one is running."""
    if info is None or not daemon_alive(info):
        console.print("No active callback tunnel.")
        return False
    console.print(f"Tunnel URL : {info['tunnel_url']}", highlight=False)
    console.print(f"Receiver   : {info['receiver_url']}", highlight=False)
    console.print(f"Daemon PID : {info['pid']}", highlight=False)
    return True


def _start() -> None:
    running = daemon_alive(info) if (info := read_tunnel_info()) is not None else False
    info, reason = start_tunnel()
    if info is None:
        console.print(f"[red]Could not start tunnel: {reason}[/]")
        raise typer.Exit(1)
    console.print(
        "[green]Callback tunnel already running.[/]"
        if running
        else "[green]Callback tunnel started.[/]"
    )
    _show_status(info)


def _stop(info: dict[str, Any] | None) -> None:
    if info is None:
        console.print("No callback tunnel to stop.")
        return
    with contextlib.suppress(ProcessLookupError):
        os.kill(int(info["pid"]), signal.SIGTERM)
    clear_tunnel_info()
    console.print("Callback tunnel stopped.")


@app.command(
    "tunnel | tun",
    help="Show the shared async-callback tunnel's status, or start/stop it.",
)
def tunnel(
    action: Annotated[
        _Action | None,
        typer.Argument(help="'start' or 'stop'; omit to show status (and prompt)."),
    ] = None,
) -> None:
    """Show the shared callback tunnel's status, or start/stop it."""
    if action == _Action.start:
        _start()
        return

    info = read_tunnel_info()
    if action == _Action.stop:
        _stop(info)
        return

    running = _show_status(info)
    if not is_interactive():
        return
    with redirect_stdout(stderr):
        if running:
            if ConfirmPrompt(message="Stop the tunnel?", default=False).execute():
                _stop(info)
        elif ConfirmPrompt(message="Start the tunnel?", default=True).execute():
            _start()
