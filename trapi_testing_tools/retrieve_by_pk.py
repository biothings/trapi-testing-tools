import ast
import asyncio
import json
from collections import Counter
from contextlib import redirect_stdout
from http import HTTPStatus
from pathlib import Path
from sys import stderr
from typing import Any, Literal

import httpx
from InquirerPy.prompts.confirm import ConfirmPrompt
from InquirerPy.prompts.fuzzy import FuzzyPrompt
from rich import box, progress
from rich.table import Table
from rich.text import Text

from tests.battery import standard_battery
from trapi_testing_tools.config import CONFIG
from trapi_testing_tools.console import console
from trapi_testing_tools.fetch import FetchProgress, fetch, live_rows, stream_into
from trapi_testing_tools.run_query import run_tests
from trapi_testing_tools.types import Query
from trapi_testing_tools.utils import (
    SYNC_BASIC_CLIENT,
    IndentedBlock,
    handle_output,
)

ARS_MESSAGES_PATH = "/ars/api/messages"


def _new_async_client() -> httpx.AsyncClient:
    """A fresh ARS async client, opened/closed per fan-out so no loop-bound client leaks."""
    return httpx.AsyncClient(follow_redirects=True, timeout=300)


def _ars_messages_url(base: str) -> str:
    """Build the ARS messages endpoint from an environment's base URL."""
    return f"{base.rstrip('/')}{ARS_MESSAGES_PATH}"


def _agent_name(child: dict[str, Any]) -> str:
    """Actor agent name for a trace child, or an empty string when absent."""
    return str((child.get("actor") or {}).get("agent") or "")


async def check_ars_pk(
    client: httpx.AsyncClient, lvl: str, pk: str, status: progress.Progress
) -> dict[str, Any] | None:
    """Check the ars for a given pk, skipping the level if it can't be reached."""
    task = status.add_task(f"Querying ARS {lvl.capitalize()}...", total=1)

    try:
        base = _ars_messages_url(CONFIG.environments["ars"][lvl])
        response = await client.get(f"{base}/{pk}?trace=y")
        response.raise_for_status()
    except httpx.HTTPStatusError as error:
        code = error.response.status_code
        label = "404" if code == HTTPStatus.NOT_FOUND else f"skipped ({code})"
        status.update(
            task, description=f"[red]x[/] ARS {lvl.capitalize()} {label}", completed=1
        )
        return None
    except httpx.HTTPError:
        status.update(
            task,
            description=f"[yellow]-[/] ARS {lvl.capitalize()} unreachable, skipped",
            completed=1,
        )
        return None

    try:
        body = response.json()
    except ValueError:
        status.update(
            task,
            description=f"[yellow]-[/] ARS {lvl.capitalize()} returned a non-JSON body, skipped",
            completed=1,
        )
        return None

    status.update(
        task,
        description=f"[green]✓[/] ARS {lvl.capitalize()} has response",
        completed=1,
    )
    return body


def get_ars_trace(pk: str) -> tuple[str, dict[str, Any]]:
    """Query the ARS instances until the pk is found, returning the trace."""
    levels = list(CONFIG.environments["ars"].keys())
    task_group = progress.Progress(
        progress.SpinnerColumn(finished_text=""),
        progress.TextColumn("{task.description}"),
        console=console,
    )

    async def _gather() -> list[dict[str, Any] | None]:
        async with _new_async_client() as client:
            return await asyncio.gather(
                *(check_ars_pk(client, lvl, pk, task_group) for lvl in levels)
            )

    with task_group:
        responses = dict(zip(levels, asyncio.run(_gather()), strict=True))

        for lvl, response in responses.items():
            if response is not None:
                return CONFIG.environments["ars"][lvl], response

        console.print("Unable to find PK on any ARS instances.")
        return "", {}


def get_ars_ara_response(
    target_ars: str, trace: dict[str, Any], ara: str | None
) -> tuple[dict[str, Any], str]:
    """Select an ARA-specific response from the ARS trace and retrieve it.

    Returns the stored response body along with the selected actor's full agent
    name (e.g. `ara-shepherd-bte`) for cross-referencing the merge history.
    """
    children = _ara_children(trace)
    actors = [_agent_name(child).removeprefix("ara-") for child in children]

    if ara in actors:
        selection = ara
    else:
        if ara is not None:
            console.print(
                f"Warning: pre-selected ara '{ara}' not a valid actor", style="yellow"
            )
        selection = FuzzyPrompt(
            message="Select ARA to retrieve response of:",
            choices=actors,
            border=True,
            instruction="(Type to filter, Tab to select, Enter to confirm)",
            info=True,
        ).execute()

    actor = next(
        child
        for child in children
        if _agent_name(child).removeprefix("ara-") == selection
    )

    message_id = actor.get("message")
    if not message_id:
        raise ValueError(f"ARA '{selection}' has no stored message in the trace")

    response = fetch(
        SYNC_BASIC_CLIENT, "GET", f"{_ars_messages_url(target_ars)}/{message_id}"
    )
    response.raise_for_status()
    console.print(f"Got ARS stored response for {selection}")
    return response.json(), _agent_name(actor)


def _merge_steps(container: dict[str, Any]) -> list[tuple[str, str]]:
    """Parse a stringified `merged_versions_list` into (merged_pk, agent) pairs.

    The ARS stores this as a `repr`'d Python list (single-quoted), so it is read
    with `ast.literal_eval` rather than `json`.
    """
    raw = container.get("merged_versions_list")
    if not raw:
        return []
    steps = raw
    if isinstance(raw, str):
        try:
            steps = ast.literal_eval(raw)
        except (ValueError, SyntaxError):
            return []
    return [
        (str(step[0]), str(step[1]))
        for step in steps
        if isinstance(step, list | tuple) and len(step) >= 2  # noqa:PLR2004
    ]


def _merge_counts(container: dict[str, Any]) -> Counter[str]:
    """Tally merge steps per agent from a `merged_versions_list`."""
    return Counter(agent for _pk, agent in _merge_steps(container))


def _status_style(status: str | None) -> str:
    """Map an ARS/TRAPI status string to a rich style."""
    lowered = (status or "").lower()
    if lowered in ("done", "success"):
        return "green"
    if lowered in ("error", "failed"):
        return "red"
    return "yellow"


def print_ars_metadata(
    body: dict[str, Any], merge_count: int | None = None, *, show_pk: bool = True
) -> None:
    """Print key ARS metadata from a raw ARS stored response to the terminal.

    `merge_count` is the number of times this ARA was merged into the parent PK,
    derived from the parent trace since a child response omits its own history.
    `show_pk` omits the PK row when the caller already surfaces it in a header.
    """
    fields: dict[str, Any] = body.get("fields", {})
    data: dict[str, Any] = fields.get("data", {})
    message: dict[str, Any] = data.get("message") or {}
    result_stat: dict[str, Any] = fields.get("result_stat") or {}

    ara_status = fields.get("status")
    trapi_status = data.get("status")
    results = fields.get("result_count")
    if results is None:
        results = len(message.get("results") or [])

    table = Table(box=None, show_header=False, pad_edge=False)
    table.add_column("Field", style="rule.line", justify="left")
    table.add_column("Value", overflow="fold")

    if show_pk:
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
    if merge_count is None:
        merge_count = sum(_merge_counts(fields).values())
    table.add_row("Merges", str(merge_count))
    table.add_row("Timestamp", str(fields.get("timestamp") or "—"))
    table.add_row("Updated At", str(fields.get("updated_at") or "—"))

    console.print(table)


def print_status_close(status: str | None) -> None:
    """Print the `└ <status>` line closing an indented metadata block.

    Callers emit this after any view/save interaction so the prompt can't clobber it.
    """
    console.print(
        f"└ [{_status_style(status)}]{status or '—'}[/]",
        style="rule.line",
        markup=True,
    )


def print_trace_metadata(trace: dict[str, Any]) -> str | None:
    """Print key ARS metadata from a raw ARS trace; returns the trace status.

    The caller prints the closing `└` line (via `print_status_close`) once any
    view/save interaction is done, so an interactive prompt can't overwrite it.
    """
    children: list[dict[str, Any]] = trace.get("children") or []
    status = trace.get("status")
    merge_counts = _merge_counts(trace)
    pk = str(trace.get("pk") or trace.get("message") or "—")

    console.print(Text("┌ ", style="rule.line") + f"ARS Trace Metadata · {pk}")
    console.push_render_hook(IndentedBlock())

    table = Table(box=None, show_header=False, pad_edge=False)
    table.add_column("Field", style="rule.line", justify="left")
    table.add_column("Value", overflow="fold")

    table.add_row(
        "Status",
        f"[{_status_style(status)}]{status or '—'}[/]",
    )
    table.add_row("Actors", str(len(children)))
    table.add_row("Merges", str(sum(merge_counts.values())))
    table.add_row("Merged Version", str(trace.get("merged_version") or "—"))

    console.print(table)

    if children:
        console.print(Text(""))
        actor_table = Table(box=box.SIMPLE, pad_edge=False, show_edge=False)
        actor_table.add_column("Actor", overflow="fold")
        actor_table.add_column("Status")
        actor_table.add_column("Code", justify="right")
        actor_table.add_column("Results", justify="right")
        actor_table.add_column("Merges", justify="right")

        for child in children:
            actor = child.get("actor") or {}
            child_status = child.get("status")
            agent_full = str(actor.get("agent") or "")
            agent = agent_full.removeprefix("ara-").removeprefix("kp-") or "—"
            actor_table.add_row(
                agent,
                f"[{_status_style(child_status)}]{child_status or '—'}[/]",
                str(child.get("code") if child.get("code") is not None else "—"),
                str(
                    child.get("result_count")
                    if child.get("result_count") is not None
                    else "—"
                ),
                str(merge_counts.get(agent_full, 0)),
            )

        console.print(actor_table)

    console.pop_render_hook()
    return status


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


def _ara_children(trace: dict[str, Any]) -> list[dict[str, Any]]:
    """The trace's ARA child actors (those whose agent name marks them as an ARA)."""
    return [
        child
        for child in trace.get("children") or []
        if "ara" in str((child.get("actor") or {}).get("agent") or "")
    ]


async def _fetch_actor_response(
    client: httpx.AsyncClient,
    target_url: str,
    child: dict[str, Any],
    progress: FetchProgress,
) -> tuple[str, dict[str, Any] | None, Exception | None]:
    """Stream one actor's stored response into `progress`, returning (agent, body, error)."""
    agent = _agent_name(child) or "unknown"
    try:
        response = await stream_into(
            client,
            "GET",
            f"{_ars_messages_url(target_url)}/{child.get('message')}",
            progress,
        )
        response.raise_for_status()
        return agent, response.json(), None
    except (httpx.HTTPError, ValueError) as error:
        return agent, None, error


def _fetch_all_actor_responses(
    target_url: str, children: list[dict[str, Any]]
) -> list[tuple[str, dict[str, Any] | None, Exception | None]]:
    """Concurrently fetch every actor's stored response, one live progress bar each."""
    rows = [
        FetchProgress(label=_agent_name(child).removeprefix("ara-"))
        for child in children
    ]

    async def _gather() -> list[tuple[str, dict[str, Any] | None, Exception | None]]:
        async with _new_async_client() as client:
            return await asyncio.gather(
                *(
                    _fetch_actor_response(client, target_url, child, row)
                    for child, row in zip(children, rows, strict=True)
                )
            )

    with live_rows(rows):
        return asyncio.run(_gather())


def _run_battery(payload: dict[str, Any]) -> tuple[int, int]:
    """Run the standard battery against a payload, printing tt-test-style lines.

    Returns the (passed, failed) counts.
    """
    http_response = httpx.Response(200, content=json.dumps(payload).encode())
    query = Query(tests=standard_battery())
    passed, failed, _ = run_tests(query, http_response)
    return passed, failed


def _battery_verdict(passed: int, failed: int) -> str:
    """Format the `└`-line verdict for one ARA's battery (mirrors the test runner)."""
    if failed == 0:
        return "[green]✓ Passed[/]"
    message = f"[red]X Failed[/] {failed}"
    if passed > 0:
        message += f"[white] ─ [/][green]Passed[/] {passed}"
    return message


def _save_triage_response(
    save_path: Path, agent: str, body: dict[str, Any], *, prefix: bool, raw: bool
) -> Path:
    """Write one ARA's triage response to `save_path`, returning the path written.

    Mirrors `tt test`'s multi-save — `save_path` is a file, actor-prefixed
    (`<ara>_<name>`) when `prefix` — saving the raw ARS body when `raw`, else the payload.
    """
    payload = body if raw else extract_response_payload(body)

    path = save_path
    if prefix:
        path = path.with_name(f"{agent.removeprefix('ara-')}_{path.name}")

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf8") as file:
        json.dump(payload, file)
    return path


def run_triage(pk: str, save_path: Path | None = None, raw: bool = False) -> None:
    """Retrieve every ARA response for a PK and show metadata + battery for each.

    When `save_path` is set, each fetched response is also persisted to it (actor-
    prefixed when there's more than one; the raw ARS body when `raw`, else the payload).
    """
    try:
        target_url, trace_body = get_ars_trace(pk)
        if target_url == "":
            return
    except httpx.HTTPError as error:
        handle_error("Failed to get ARS trace for pk", error)
        return

    print_status_close(print_trace_metadata(trace_body))

    children = _ara_children(trace_body)
    if not children:
        console.print("No ARA actors found in trace.")
        return

    merge_counts = _merge_counts(trace_body)
    prefix = len(children) > 1
    for agent, body, error in _fetch_all_actor_responses(target_url, children):
        console.rule(
            Text("┌ ", style="rule.line") + agent.removeprefix("ara-"), align="left"
        )
        if body is None:
            console.print(f"└ [red]failed to retrieve: {error!r}[/]", style="rule.line")
            continue

        console.push_render_hook(IndentedBlock())
        print_ars_metadata(body, merge_counts.get(agent, 0))
        passed, failed = _run_battery(extract_response_payload(body))
        if save_path is not None:
            path = _save_triage_response(save_path, agent, body, prefix=prefix, raw=raw)
            console.print(Text(f"Saved to {path}", style="rule.line"))
        console.pop_render_hook()

        console.print(
            f"└ {_battery_verdict(passed, failed)}", style="rule.line", markup=True
        )


def get_response_from_pk(  # noqa:PLR0913
    pk: str,
    ara: str | None,
    view_mode: Literal["prompt", "skip", "every", "pipe"],
    save_mode: Literal["prompt", "skip", "every"],
    save_path: Path | None,
    trace: bool = False,
    raw: bool = False,
) -> None:
    """Drill down into ARS PK to get a response of interest."""
    target_url: str
    trace_body: dict[str, Any]
    try:
        target_url, trace_body = get_ars_trace(pk)
        if target_url == "":
            return
    except httpx.HTTPError as error:
        handle_error("Failed to get ARS trace for pk", error)
        return

    if trace:
        status = print_trace_metadata(trace_body)
        handle_output(trace_body, view_mode, save_mode, save_path, subject="trace")
        print_status_close(status)
        return

    try:
        body, selected_agent = get_ars_ara_response(target_url, trace_body, ara)
    except (httpx.HTTPError, ValueError, StopIteration) as error:
        handle_error("Failed to get ARS stored response for ARA", error)
        return

    merge_count = _merge_counts(trace_body).get(selected_agent, 0)
    console.print(
        Text("┌ ", style="rule.line") + f"ARS Response Metadata · {body.get('pk', '—')}"
    )
    console.push_render_hook(IndentedBlock())
    print_ars_metadata(body, merge_count, show_pk=False)
    console.pop_render_hook()
    payload = body if raw else extract_response_payload(body)

    handle_output(payload, view_mode, save_mode, save_path)

    print_status_close(body.get("fields", {}).get("status"))
