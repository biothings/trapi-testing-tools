import asyncio
from contextlib import redirect_stdout
from pathlib import Path
from sys import stderr
from typing import Any, Literal, cast

import httpx
from InquirerPy import inquirer
from rich import progress
from rich.console import Console
from urlextract import URLExtract

from trapi_testing_tools.config import CONFIG
from trapi_testing_tools.utils import handle_output

console = Console(stderr=True)
client = httpx.AsyncClient(follow_redirects=True, timeout=300)


async def check_ars_pk(
    lvl: str, pk: str, status: progress.Progress
) -> dict[str, Any] | None:
    """Check the ars for a given pk."""
    response = await client.get(f"{CONFIG.environments['ars'][lvl]}/{pk}?trace=y")
    task = status.add_task(f"Querying ARS {lvl.capitalize()}...")

    if response.status_code == 404:
        status.update(
            task,
            description=f"[red]x[/] ARS {lvl.capitalize()} 404",
            completed=1,
        )
        return

    response.raise_for_status()
    status.update(
        task,
        description=f"[green]✓[/] ARS {lvl.capitalize()} has response",
        completed=1,
    )
    return response.json()


def get_ars_trace(pk: str) -> tuple[str, dict[str, Any]]:
    """Query the ARS instances until the pk is found, returning the trace."""
    levels = list(CONFIG.environments["ars"].keys())
    task_group = progress.Progress(
        progress.SpinnerColumn(finished_text=""),
        progress.TextColumn("{task.description}"),
        console=console,
    )
    queries = [check_ars_pk(lvl, pk, task_group) for lvl in levels]

    with task_group:
        loop = asyncio.get_event_loop()
        responses = dict(
            zip(levels, loop.run_until_complete(asyncio.gather(*queries)), strict=True)
        )

        for lvl, response in responses.items():
            if response is not None:
                return CONFIG.environments["ars"][lvl], response

        console.print("Unable to find PK on any ARS instances.")
        return "", {}


def get_ars_ara_response(
    target_ars: str, trace: dict[str, Any], ara: str | None
) -> dict[str, Any]:
    """Select an ARA-specific response from the ARS trace and retrieve it."""
    actor: dict[str, Any]
    actors = [
        child["actor"]["agent"].removeprefix("ara-")
        for child in trace["children"]
        if "ara" in child["actor"]["agent"]
    ]

    if ara in actors:
        actor = next(
            child for child in trace["children"] if ara in child["actor"]["agent"]
        )
        selection = ara
    else:
        if ara is not None:
            console.print(f"Warning: pre-selected ara '{ara}' not a valid actor")
        selection = inquirer.fuzzy(
            message="Select ARA to retrieve response of:",
            choices=[actor.removeprefix("ara-") for actor in actors],
            border=True,
            instruction="(Type to filter, Tab to select, Enter to confirm)",
            info=True,
        ).execute()
        actor = next(
            child for child in trace["children"] if selection in child["actor"]["agent"]
        )

    console.print(f"Child key for {selection}: {actor['message']}")

    with console.status("Querying ARS for TRAPI response..."):
        response = httpx.get(f"{target_ars}/{actor['message']}")
    response.raise_for_status()
    console.print(f"Got ARS stored response for {selection}")
    return response.json()


def check_logs(body: dict[str, Any]) -> dict[str, Any] | None:
    """Check logs for original response URL, prompt user to select, then retrieve response."""
    logs = body.get("fields", {}).get("data", {}).get("logs", {})
    if not logs:
        return

    extractor = URLExtract()
    possible_logs: list[str] = []
    for log in logs:  # Possible multiple URLs in one log
        urls = extractor.find_urls(log["message"])
        possible_logs.extend(
            f"{log['message'].split(url, 1)[0]} >{url}< ..." for url in urls
        )

    selection = possible_logs[0]
    if len(possible_logs) > 1:
        with redirect_stdout(stderr):
            selection = inquirer.fuzzy(
                message="Select URL from logs:",
                choices=possible_logs,
                border=True,
                instruction="(Type to filter, Tab to select, Enter to confirm)",
                info=True,
            ).execute()
    url = cast(str, extractor.find_urls(selection)[0])

    console.print(f"Response URL: {url}")
    with console.status("Querying for original response..."):
        response = httpx.get(url)
    response.raise_for_status()
    return response.json()


def handle_error(msg: str, error: Exception) -> None:
    """Print some `msg` and error name, prompting to print traceback."""
    console.print(f"ERROR: {msg} due to {error!r}")
    with redirect_stdout(stderr):
        if inquirer.confirm("Print traceback for this error?", default=False).execute():
            console.print_exception(show_locals=True)


def get_response_from_pk(
    pk: str,
    ara: str | None,
    view_mode: Literal["prompt", "skip", "every", "pipe"],
    save_mode: Literal["prompt", "skip", "every"],
    save_path: Path | None,
) -> None:
    """Drill down into ARS PK to get a response of interest."""
    target_url: str
    body: dict[str, Any]
    try:
        target_url, body = get_ars_trace(pk)
        if target_url == "":
            return
    except httpx.HTTPError as error:
        handle_error("Failed to get ARS trace for pk", error)
        return

    try:
        body = get_ars_ara_response(target_url, body, ara)
    except httpx.HTTPError as error:
        handle_error("Failed to get ARS stored response for ARA", error)
        return

    try:
        if inquirer.confirm(
            "Scan response logs for original response url?", default=False
        ).execute():
            response = check_logs(body)
            if response is not None:
                body = response
    except httpx.HTTPError as error:
        handle_error("Failed to get response from ARA", error)
        return

    handle_output(body, view_mode, save_mode, save_path)
