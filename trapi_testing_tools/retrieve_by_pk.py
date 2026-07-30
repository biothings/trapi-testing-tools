import asyncio
from contextlib import redirect_stdout
from http import HTTPStatus
from pathlib import Path
from sys import stderr
from typing import Any, Literal

import httpx
from InquirerPy.prompts.confirm import ConfirmPrompt
from InquirerPy.prompts.fuzzy import FuzzyPrompt
from rich import box, progress
from rich.console import Console
from rich.table import Table

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

    if response.status_code == HTTPStatus.NOT_FOUND:
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
        selection = FuzzyPrompt(
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


def _status_style(status: str | None) -> str:
    """Map an ARS/TRAPI status string to a rich style."""
    lowered = (status or "").lower()
    if lowered in ("done", "success"):
        return "green"
    if lowered in ("error", "failed"):
        return "red"
    return "yellow"


def print_ars_metadata(body: dict[str, Any]) -> None:
    """Print key ARS metadata from a raw ARS stored response to the terminal."""
    fields: dict[str, Any] = body.get("fields", {})
    data: dict[str, Any] = fields.get("data", {})
    message: dict[str, Any] = data.get("message") or {}
    result_stat: dict[str, Any] = fields.get("result_stat") or {}

    ara_status = fields.get("status")
    trapi_status = data.get("status")
    results = fields.get("result_count")
    if results is None:
        results = len(message.get("results") or [])

    table = Table(
        title="ARS Response Metadata",
        title_style="bold",
        box=box.SIMPLE,
        show_header=False,
    )
    table.add_column("Field", style="rule.line", justify="right")
    table.add_column("Value", overflow="fold")

    table.add_row("PK", str(body.get("pk", "—")))
    table.add_row("ARA", str(fields.get("name") or "—"))
    table.add_row(
        "ARS Status",
        f"[{_status_style(ara_status)}]{ara_status or '—'}[/] "
        f"(code {fields.get('code', '—')})",
    )
    table.add_row(
        "TRAPI Status",
        f"[{_status_style(trapi_status)}]{trapi_status}[/]" if trapi_status else "—",
    )
    table.add_row("Results", str(results))
    if result_stat:
        stats = {
            key: (round(value, 3) if isinstance(value, int | float) else value)
            for key, value in result_stat.items()
        }
        table.add_row(
            "Score Stats",
            f"min {stats.get('minimum')} / median {stats.get('median')} / "
            f"mean {stats.get('mean')} / max {stats.get('maximum')}",
        )
    table.add_row("Logs", str(len(data.get("logs") or [])))
    table.add_row(
        "Schema / Biolink",
        f"{data.get('schema_version') or '—'} / {data.get('biolink_version') or '—'}",
    )
    table.add_row("Merged Version", str(fields.get("merged_version") or "—"))
    table.add_row("Timestamp", str(fields.get("timestamp") or "—"))
    table.add_row("Updated At", str(fields.get("updated_at") or "—"))

    console.print(table)


def extract_response_payload(body: dict[str, Any]) -> dict[str, Any]:
    """Extract the TRAPI response payload from a raw ARS stored response.

    Falls back to the raw body if the expected `fields.data` shape is absent.
    """
    return body.get("fields", {}).get("data", body)


def handle_error(msg: str, error: Exception) -> None:
    """Print some `msg` and error name, prompting to print traceback."""
    console.print(f"ERROR: {msg} due to {error!r}")
    with redirect_stdout(stderr):
        if ConfirmPrompt("Print traceback for this error?", default=False).execute():
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

    print_ars_metadata(body)
    payload = extract_response_payload(body)

    handle_output(payload, view_mode, save_mode, save_path)
