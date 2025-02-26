import importlib
import time
from contextlib import redirect_stdout
from pathlib import Path
from sys import stderr
from types import ModuleType
from typing import Callable, Literal, Optional, Union, cast

import httpx
from rich.text import Text
import yaml
from InquirerPy import inquirer
from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.pretty import Pretty

import trapi_testing_tools
from trapi_testing_tools.utils import IndentedBlock, handle_output

console = Console(stderr=True)

with open(
    Path(__file__).parent.joinpath("../config.yaml").resolve(), "r"
) as config_file:
    config = yaml.safe_load(config_file)

CLIENT = httpx.Client(follow_redirects=True, timeout=config["timeout"])


def check_query_valid(query: ModuleType) -> None:
    """Check that query has required options."""
    methods = ["GET", "POST"]
    if not hasattr(query, "steps"):
        if not hasattr(query, "method") or query.method not in ["GET", "POST"]:
            console.print("query must have method defined as GET or POST")
            raise AttributeError
        if not hasattr(query, "endpoint"):
            console.print("query must have endpoint defined")
            raise AttributeError
        return
    for step in query.steps:
        if step.get("method", None) not in methods:
            console.print("query must have method defined as GET or POST")
            raise AttributeError
        if step.get("endpoint", None) is None:
            console.print("query must have endpoint defined")
            raise AttributeError


def run_query(query: dict, url: str) -> tuple[Union[httpx.Response, None], bool]:
    """Run an individual query, handling sync or async intelligently."""
    response: Optional[httpx.Response] = None
    elapsed = 0.0
    uncertainty = 0
    passed = True

    console.print(f"{query.get('method')} {url}{query.get('endpoint')}")

    try:
        with console.status("Querying..."):
            response = CLIENT.request(
                method=cast(str, query.get("method")),
                url=url + cast(str, query.get("endpoint")),
                params=query.get("params", None),
                headers=query.get("headers", None),
                json=query.get("body", None),
            )

        elapsed = response.elapsed.total_seconds()
        response.raise_for_status()
        body = cast(dict, response.json())
        console.print(f"Initial query elapsed time {elapsed}s", highlight=False)

        if "asyncquery" not in cast(str, query.get("endpoint")):
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
                body = cast(dict, response.json())
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


def run_tests(query: dict, response: httpx.Response, passed: bool) -> bool:
    """Run tests specified by query against the response."""
    for i, test in enumerate(cast(list[Callable], query.get("tests"))):
        try:
            failure_report = test(response)  # Returns report if failed otherwise None

            if not failure_report:
                console.print(f"[green]✓[/] {i + 1}. {test.__name__}")
                continue

            console.print(f"[red]x[/] {i + 1}. {test.__name__}")
            passed = False
            report_visual = Panel(
                Pretty(failure_report),
                title="failure reason",
                title_align="left",
                expand=False,
                box=box.SQUARE,
                border_style="red",
            )
            console.print(report_visual)

        except Exception as error:
            console.print(
                f"[red]![/] {i + 1}. {test.__name__}: An error occurred in this test: {repr(error)}"
            )
            with redirect_stdout(stderr):
                if inquirer.confirm(
                    "Print traceback for this error?", default=False
                ).execute():
                    console.print_exception(show_locals=True)
            passed = False

    return passed


def manage_query(
    query_module: ModuleType,
    url: str,
    view_mode: Literal["prompt", "skip", "every", "pipe"],
    save_mode: Literal["prompt", "skip", "every"],
    save_path: Optional[Path],
    on_fail: bool,
) -> None:
    """Interpret query as single or multiple and manage steps in running it."""
    console.rule(
        Text("┌ ", style="rule.line")
        + str(
            Path(cast(str, query_module.__file__)).relative_to(
                Path(trapi_testing_tools.__path__[0]) / "queries"
            )
        ),
        align="left",
    )
    console.push_render_hook(IndentedBlock())

    check_query_valid(query_module)

    queries: list[dict]
    if hasattr(query_module, "steps"):
        queries = query_module.steps
    else:
        queries = [
            dict(
                method=getattr(query_module, "method", None),
                headers=getattr(query_module, "headers", None),
                endpoint=getattr(query_module, "endpoint", None),
                params=getattr(query_module, "params", None),
                body=getattr(query_module, "body", None),
                tests=getattr(query_module, "tests", None),
            )
        ]

    response: Optional[httpx.Response] = httpx.Response(200)
    passed: bool = True
    for query in queries:
        response, passed = run_query(query, url)
        if not response:
            console.pop_render_hook()
            console.print("└ No Response", style="rule.line")
            return

        if passed and query.get("tests", False):
            passed = run_tests(query, response, passed)

    # Output
    if on_fail and passed:
        view_mode = "skip"
        save_mode = "skip"

    try:
        output = cast(dict, response.json())
    except Exception:
        output = response.text

    handle_output(output, view_mode, save_mode, save_path)

    console.pop_render_hook()
    console.print(
        f"└ {'[green]✓ Tests Passed[/]' if passed else '[red]x Failed[/]'}",
        style="rule.line",
        markup=True,
    )


def run_queries(
    files: list[Path],
    url: str,
    view_mode: Literal["prompt", "skip", "every", "pipe"],
    save_mode: Literal["prompt", "skip", "every"],
    save_path: Optional[Path] = None,
    on_fail: bool = False,
) -> None:
    """Given a set of queries, run each."""
    for file in files:
        file = file.resolve().relative_to(Path(trapi_testing_tools.__path__[0]).parent)
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
            query = importlib.import_module(".".join(file.with_suffix("").parts))
        except Exception as error:
            console.print(
                f"ERROR: failed to read query file due to {repr(error)}. The query will be skipped."
            )
            with redirect_stdout(stderr):
                if inquirer.confirm(
                    "Print traceback for this error?", default=False
                ).execute():
                    console.print_exception(show_locals=True)
            continue
        manage_query(query, url, view_mode, save_mode, save_path, on_fail)
