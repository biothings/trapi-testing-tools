import importlib
import time
from contextlib import redirect_stdout
from pathlib import Path
from sys import stderr
from types import ModuleType
from typing import Any, cast

import httpx
import yaml
from InquirerPy import inquirer
from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.pretty import Pretty
from rich.text import Text

import trapi_testing_tools
from trapi_testing_tools.types import OutputModes, Query
from trapi_testing_tools.utils import IndentedBlock, handle_output, parse_query

console = Console(stderr=True)

with open(Path(__file__).parent.joinpath("../config.yaml").resolve()) as config_file:
    config = yaml.safe_load(config_file)

CLIENT = httpx.Client(follow_redirects=True, timeout=config["timeout"])


def run_queries(
    files: list[Path],
    url: str,
    output_modes: OutputModes,
    save_path: Path | None = None,
    on_fail: bool = False,
) -> None:
    """Given a set of queries, run each."""
    for path in files:
        file = path.resolve().relative_to(Path(trapi_testing_tools.__path__[0]).parent)
        if file.suffix != ".py":
            console.print(
                f"INFO: skipping {file} as it is not a python file",
                style="italic bright_black",
            )
            continue
        if not file.exists():
            console.print(f"ERROR: {file} does not exist. Skipping...", style="red")
            continue
        try:
            import_path = ".".join(file.with_suffix("").parts)
            query = importlib.import_module(import_path)
        except Exception as error:
            console.print(
                f"ERROR: failed to read query file due to {error!r}. The query will be skipped."
            )
            with redirect_stdout(stderr):
                if inquirer.confirm(
                    "Print traceback for this error?", default=False
                ).execute():
                    console.print_exception(show_locals=True)
            continue
        manage_query(query, url, output_modes, save_path, on_fail)


def manage_query(
    query_module: ModuleType,
    url: str,
    output_modes: OutputModes,
    save_path: Path | None,
    on_fail: bool,
) -> None:
    """Interpret query as single or multiple and manage steps in running it."""
    view_mode, save_mode = output_modes

    # Use rich text behavior to create a section for this query's context
    console.rule(
        Text("┌ ", style="rule.line")
        + str(
            Path(cast(str, query_module.__file__)).relative_to(
                Path(trapi_testing_tools.__path__[0]).parent
            )
        ),
        align="left",
    )
    console.push_render_hook(IndentedBlock())

    queries = parse_query(query_module)

    response: httpx.Response | None = httpx.Response(200)
    passed: bool = True
    n_passed: int | None = None
    n_failed: int | None = None
    for query in queries:
        response, passed = run_query(query, url)
        if not response:
            console.pop_render_hook()
            console.print("└ No Response", style="rule.line")
            return

        if passed and query.tests is not None:
            n_passed, n_failed = run_tests(query, response)
            passed = n_failed == 0

    # Output
    if on_fail and passed:
        view_mode = "skip"
        save_mode = "skip"

    try:
        output = cast(dict[str, Any], response.json())
    except Exception:
        output = response.text

    handle_output(output, view_mode, save_mode, save_path)

    console.pop_render_hook()

    message = "[green]✓ Passed[/]" if passed else "[red]X Failed[/]"

    if not passed and isinstance(n_passed, int):
        message += f" {n_failed}"
        if n_passed > 0:
            message += f"[white] ─ [/][green]Passed[/] {n_passed}"

    console.print(
        f"└ {message}",
        style="rule.line",
        markup=True,
    )


def run_query(query: Query, url: str) -> tuple[httpx.Response | None, bool]:
    """Run an individual query, handling sync or async intelligently."""
    response: httpx.Response | None = None
    elapsed = 0.0
    uncertainty = 0
    passed = True

    console.print(f"{query.method} {url}{query.endpoint}")

    try:
        with console.status("Querying..."):
            response = CLIENT.request(
                method=cast(str, query.method),
                url=url + cast(str, query.endpoint),
                params=query.params,
                headers=query.headers,
                json=query.body,
            )

        elapsed = response.elapsed.total_seconds()
        response.raise_for_status()
        body = cast(dict[str, Any], response.json())
        console.print(f"Initial query elapsed time {elapsed}s", highlight=False)

        if "asyncquery" not in cast(str, query.endpoint):
            return response, passed

        status_url = url + "/asyncquery_status/" + body["job_id"]
        status = body["status"]

        # Poll for response from async status endpoint
        with console.status("Polling status endpoint every 10s...") as task_status:
            timeout = time.time() + config["timeout"]
            timed_out = False
            attempt = 0
            console.print(f"GET {status_url} (polling)")

            while status in ["Accepted", "Queued", "Running"]:
                if time.time() > timeout:
                    timed_out = True
                    break

                if attempt > 0:
                    time.sleep(10)
                    elapsed += 10
                    uncertainty = 10  # Could have finished any time in interval

                attempt += 1
                task_status.update(f"Polling status endpoint every 10s...({attempt})")
                response = CLIENT.get(status_url)
                response.raise_for_status()
                body = cast(dict[str, Any], response.json())
                status = body["status"]

        if timed_out:
            console.print("Query timed out.")
            passed = False
            return response, passed

        response_url = body.get("response_url", None)
        if response_url is None:
            console.print("No response url found, query may have failed.")
            return response, passed

        with console.status("Querying response endpoint..."):
            console.print(f"GET {response_url}")
            response = CLIENT.get(response_url)
            response.raise_for_status()
            elapsed += response.elapsed.total_seconds()

    except httpx.HTTPStatusError as error:
        console.print(error)
        response = error.response
    except httpx.RequestError as error:
        console.print("Query failed due to an exception, information below:")
        console.print(error)
        passed = False

    console.print(
        f"total query elapsed time: {elapsed} (±{uncertainty})s", highlight=False
    )
    return response, passed


def run_tests(query: Query, response: httpx.Response) -> tuple[int, int]:
    """Run tests specified by query against the response."""
    passed = 0
    failed = 0

    for i, test in enumerate(query.tests or []):
        try:
            result = test.test(response)  # Returns report if failed otherwise None

            message = ""

            if result.passed:
                message += "[green]✓[/]"
                passed += 1
            else:
                message += "[red]x[/]"
                failed += 1

            test_name = (
                test.__doc__.removesuffix(".") if test.__doc__ else test.__name__
            )
            message += f" {i + 1}. {test_name}"

            report_long: Panel | None = None
            if result.info:
                if isinstance(result.info, str) and "\n" not in result.info:
                    message += f" ({result.info})"
                else:
                    report_long = Panel(
                        Pretty(result.info),
                        title="details",
                        title_align="left",
                        expand=False,
                        box=box.SQUARE,
                        border_style="red",
                    )

            console.print(message)
            if report_long:
                console.print(report_long)

        except Exception as error:
            console.print(
                f"[red]![/] {i + 1}. {test.__name__}: An error occurred in this test: {error!r}"
            )
            with redirect_stdout(stderr):
                if inquirer.confirm(
                    "Print traceback for this error?", default=False
                ).execute():
                    console.print_exception(show_locals=True)
            failed += 1

    return passed, failed
