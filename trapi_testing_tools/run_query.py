import importlib
import time
from dataclasses import replace
from pathlib import Path
from types import ModuleType
from typing import Any, Literal, cast

import httpx
from rich import box
from rich.panel import Panel
from rich.text import Text

import trapi_testing_tools
from trapi_testing_tools.callback import (
    PLACEHOLDER_CALLBACK,
    CallbackSession,
    callback_session,
    make_synthetic_response,
)
from trapi_testing_tools.config import CONFIG
from trapi_testing_tools.report import (
    PipeMode,
    QueryResult,
    StepResult,
    StepRun,
    TestOutcome,
    build_query_result,
    build_step,
    emit_report,
    pre_run_failure,
)
from trapi_testing_tools.trapi_models import use_version
from trapi_testing_tools.types import OutputModes, Query
from trapi_testing_tools.utils import (
    IndentedBlock,
    console,
    format_size,
    handle_output,
    maybe_print_traceback,
    parse_query,
)

CLIENT = httpx.Client(
    follow_redirects=True, timeout=CONFIG.timeout if CONFIG.timeout >= 0 else None
)

# The status endpoint can 404 briefly before the server stores the (working) job.
_MAX_STATUS_NOT_FOUND = 3


def run_queries(  # noqa: PLR0913
    files: list[Path],
    targets: list[tuple[str, str]],
    output_modes: OutputModes,
    save_path: Path | None = None,
    on_fail: bool = False,
    pipe_mode: PipeMode | None = None,
    callback_mode: str | None = None,
) -> bool:
    """Given a set of queries, run each against each target environment.

    ``targets`` is a list of ``(env_name, url)`` pairs; every query runs against
    every target, sequentially. Returns ``True`` only if every run passed. When
    piping (``pipe_mode`` set), stdout gets either the response body/bodies
    (`PipeMode.plain`) or one aggregate `RunReport` envelope (`report`/`full`).
    """
    collect = output_modes[0] == "pipe"  # only collect responses on pipe (save mem)
    report_queries: list[QueryResult] = []
    run_start = time.monotonic()

    all_passed = True
    multiple = len(files) > 1 or len(targets) > 1
    with callback_session(callback_mode) as session:
        for path in files:
            file = path.resolve().relative_to(
                Path(trapi_testing_tools.__path__[0]).parent
            )
            if file.suffix != ".py":
                console.print(
                    f"INFO: skipping {file} as it is not a python file",
                    style="italic bright_black",
                )
                continue
            if not file.exists():
                console.print(f"ERROR: {file} does not exist. Skipping...", style="red")
                all_passed = False
                if collect:
                    report_queries.extend(
                        pre_run_failure(file, env, "file does not exist")
                        for env, _url in targets
                    )
                continue
            try:
                import_path = ".".join(file.with_suffix("").parts)
                query = importlib.import_module(import_path)
            except Exception as error:
                console.print(
                    f"ERROR: failed to read query file due to {error!r}. The query will be skipped."
                )
                maybe_print_traceback()
                all_passed = False
                if collect:
                    report_queries.extend(
                        pre_run_failure(file, env, repr(error)) for env, _url in targets
                    )
                continue

            qualified = ".".join(file.with_suffix("").parts).removeprefix("queries.")
            for env, url in targets:
                query_save_path = save_path
                if query_save_path is not None and multiple:
                    # Prefix by environment and/or query path so runs don't collide.
                    prefix = ".".join(
                        ([env] if len(targets) > 1 else [])
                        + ([qualified] if len(files) > 1 else [])
                    )
                    query_save_path = query_save_path.with_name(
                        f"{prefix}_{query_save_path.name}"
                    )
                passed, result = manage_query(
                    query,
                    url,
                    env,
                    output_modes,
                    query_save_path,
                    on_fail,
                    pipe_mode,
                    session,
                )
                if not passed:
                    all_passed = False
                if collect and result is not None:
                    report_queries.append(result)

    if collect:
        emit_report(
            report_queries,
            [env for env, _url in targets],
            all_passed,
            time.monotonic() - run_start,
            pipe_mode or PipeMode.full,
        )
    return all_passed


def manage_query(  # noqa: PLR0913
    query_module: ModuleType,
    url: str,
    env: str,
    output_modes: OutputModes,
    save_path: Path | None,
    on_fail: bool,
    pipe_mode: PipeMode | None,
    session: CallbackSession | None = None,
) -> tuple[bool, QueryResult | None]:
    """Interpret query as single or multiple and manage steps in running it.

    Returns whether the query (and any tests it defines) passed, plus a
    `QueryResult` when piping (for the aggregate report), else ``None``.
    """
    collect = output_modes[0] == "pipe"
    include_response = pipe_mode is not PipeMode.report

    rel_path = Path(cast(str, query_module.__file__)).relative_to(
        Path(trapi_testing_tools.__path__[0]).parent
    )
    # Use rich text to create a section for this query's context
    console.rule(
        Text("┌ ", style="rule.line") + str(rel_path) + f" · {env}", align="left"
    )
    console.push_render_hook(IndentedBlock())

    queries = parse_query(query_module)

    steps: list[StepResult] = []
    query_passed = True
    total_passed = 0
    total_failed = 0
    any_tests = False
    query_elapsed = 0.0
    final_response: httpx.Response | None = None

    for query in queries:
        run = run_query(query, url, session)
        final_response = run.response
        query_elapsed += run.elapsed

        if run.response is None:
            query_passed = False
            if collect:
                steps.append(
                    build_step(
                        run,
                        step_passed=False,
                        tests_passed=True,
                        include_response=include_response,
                    )
                )
            console.pop_render_hook()
            console.print("└ No Response", style="rule.line")
            result = (
                build_query_result(
                    rel_path, env, steps, False, query_elapsed, len(queries) > 1
                )
                if collect
                else None
            )
            return False, result

        step_ok = run.status == "ok"
        outcomes: list[TestOutcome] = []
        tests_passed = True
        if step_ok and query.tests is not None:
            any_tests = True
            with use_version(query.trapi_version):
                n_passed, n_failed, outcomes = run_tests(query, run.response)
            total_passed += n_passed
            total_failed += n_failed
            tests_passed = n_failed == 0

        step_passed = step_ok and tests_passed
        query_passed = query_passed and step_passed

        if collect:
            steps.append(
                build_step(
                    run,
                    step_passed,
                    tests_passed,
                    outcomes,
                    include_response=include_response,
                )
            )

    console.pop_render_hook()

    # Output (non-pipe only; piping is aggregated into one report by run_queries)
    if not collect:
        _emit_output(final_response, output_modes, save_path, on_fail, query_passed)

    _print_verdict(query_passed, any_tests, total_passed, total_failed)

    # In debug mode, keep responses only for failing queries (the ones to inspect).
    if collect and on_fail and query_passed:
        for step in steps:
            step.pop("response", None)

    result = (
        build_query_result(
            rel_path, env, steps, query_passed, query_elapsed, len(queries) > 1
        )
        if collect
        else None
    )
    return query_passed, result


def _emit_output(
    response: httpx.Response | None,
    output_modes: OutputModes,
    save_path: Path | None,
    on_fail: bool,
    passed: bool,
) -> None:
    """View/save the final response of a non-piping run."""
    view_mode, save_mode = output_modes
    if on_fail and passed:
        view_mode = "skip"
        save_mode = "skip"
    resp = cast(httpx.Response, response)
    try:
        output = cast(dict[str, Any], resp.json())
    except Exception:
        output = resp.text
    handle_output(output, view_mode, save_mode, save_path)


def _print_verdict(
    passed: bool, any_tests: bool, total_passed: int, total_failed: int
) -> None:
    """Print the query's final pass/fail summary line."""
    message = "[green]✓ Passed[/]" if passed else "[red]X Failed[/]"
    if not passed and any_tests:
        message += f" {total_failed}"
        if total_passed > 0:
            message += f"[white] ─ [/][green]Passed[/] {total_passed}"
    console.print(f"└ {message}", style="rule.line", markup=True)


def run_query(
    query: Query, url: str, session: CallbackSession | None = None
) -> StepRun:
    """Run an individual query, handling sync or async intelligently."""
    is_async = "asyncquery" in (query.endpoint or "")
    callback_token: str | None = None
    if is_async:
        query, callback_token = _prepare_async_callback(query, url, session)

    target = url + cast(str, query.endpoint)
    method = cast(str, query.method)
    elapsed = 0.0

    console.print(f"{method} {target}")

    try:
        with console.status("Querying..."):
            response = CLIENT.request(
                method=method,
                url=target,
                params=query.params,
                headers=query.headers,
                json=query.body,
            )

        elapsed = response.elapsed.total_seconds()
        response.raise_for_status()
        body = cast(dict[str, Any], response.json())
        console.print(
            f"Query elapsed time {elapsed} s · {format_size(len(response.content))}"
        )

        if not is_async:
            return StepRun(
                response, "ok", response.status_code, None, elapsed, target, method
            )

        if callback_token is not None:
            job_id = body.get("job_id") if isinstance(body, dict) else None
            if job_id:
                console.print(f"Status URL: {url}/asyncquery_status/{job_id}")
            response, status, elapsed = _await_callback_result(
                cast(CallbackSession, session), callback_token, response, elapsed
            )
        else:
            response, status, elapsed = _await_async_result(
                response, body, url, elapsed
            )
        http_status = response.status_code if response is not None else None
        return StepRun(response, status, http_status, None, elapsed, target, method)

    except httpx.HTTPStatusError as error:
        console.print(error)
        errored = error.response
        console.print(
            f"total query elapsed time: {elapsed} (±0)s · {format_size(len(errored.content))}",
            highlight=False,
        )
        return StepRun(
            errored, "ok", errored.status_code, None, elapsed, target, method
        )
    except httpx.RequestError as error:
        console.print("Query failed due to an exception, information below:")
        console.print(error)
        status = "timeout" if isinstance(error, httpx.TimeoutException) else "error"
        console.print(f"total query elapsed time: {elapsed} (±0)s", highlight=False)
        return StepRun(None, status, None, repr(error), elapsed, target, method)


def _prepare_async_callback(
    query: Query, url: str, session: CallbackSession | None
) -> tuple[Query, str | None]:
    """Inject a receiver callback into an async body when TTT owns the callback.

    Returns the (possibly rewritten) query and a token to await, or a ``None`` token for
    the poll path (an author-set callback is respected; poll gets a placeholder).
    """
    if not isinstance(query.body, dict):
        return query, None
    if query.body.get("callback"):
        return query, None

    mode = session.prepare(url) if session is not None else "poll"
    if mode == "poll":
        console.print(f"Callback: {PLACEHOLDER_CALLBACK} (placeholder; polling for result)")
        return replace(
            query, body={**query.body, "callback": PLACEHOLDER_CALLBACK}
        ), None

    assert session is not None  # a non-poll mode is only returned when a session exists
    token, callback_url = session.callback_for(mode)
    console.print(f"Callback: {callback_url}")
    return replace(query, body={**query.body, "callback": callback_url}), token


def _await_callback_result(
    session: CallbackSession, token: str, ack: httpx.Response, elapsed: float
) -> tuple[httpx.Response, Literal["ok", "timeout"], float]:
    """Block on the receiver for the service's callback POST, then wrap it."""
    start = time.monotonic()
    with console.status("Awaiting callback..."):
        console.print(f"Awaiting callback (up to {CONFIG.timeout} s)...")
        raw = session.wait(token, CONFIG.timeout)
    elapsed += time.monotonic() - start

    if raw is None:
        console.print("Callback not received before timeout.")
        return ack, "timeout", elapsed

    response = make_synthetic_response(raw)
    console.print(
        f"total query elapsed time: {elapsed}s  ·  {format_size(len(response.content))}",
        highlight=False,
    )
    return response, "ok", elapsed


def _await_async_result(
    response: httpx.Response, body: dict[str, Any], url: str, elapsed: float
) -> tuple[httpx.Response | None, Literal["ok", "timeout"], float]:
    """Poll asyncquery_status to completion, then fetch the final response."""
    status_url = url + "/asyncquery_status/" + body["job_id"]

    response, body, elapsed, uncertainty, timed_out = _poll_async_status(
        status_url, response, body, elapsed
    )

    if timed_out:
        console.print("Query timed out.")
        return response, "timeout", elapsed

    response_url = body.get("response_url", None)
    if response_url is None:
        console.print("No response url found, query may have failed.")
        return response, "ok", elapsed

    with console.status("Querying response endpoint..."):
        console.print(f"GET {response_url}")
        response = CLIENT.get(response_url)
        response.raise_for_status()
        elapsed += response.elapsed.total_seconds()

    console.print(
        f"total query elapsed time: {elapsed} (±{uncertainty})s"
        f"  ·  {format_size(len(response.content))}",
        highlight=False,
    )
    return response, "ok", elapsed


def _poll_async_status(
    status_url: str, response: httpx.Response, body: dict[str, Any], elapsed: float
) -> tuple[httpx.Response, dict[str, Any], float, int, bool]:
    """Poll every 10s while Accepted/Queued/Running (tolerating early 404s); stop on finish/timeout.

    Returns the latest response and body, the accumulated elapsed time and its
    uncertainty, and whether polling timed out.
    """
    status = body["status"]
    uncertainty = 0
    not_found = 0
    with console.status("Polling status endpoint every 10s...") as task_status:
        deadline = time.time() + CONFIG.timeout
        attempt = 0
        console.print(f"GET {status_url} (polling)")

        while status in ["Accepted", "Queued", "Running"]:
            if time.time() > deadline:
                return response, body, elapsed, uncertainty, True

            if attempt > 0:
                # 404 retries back off quickly (1s, 2s, ...); normal polls wait 10s.
                wait = not_found or 10
                time.sleep(wait)
                elapsed += wait
                uncertainty = wait

            attempt += 1
            task_status.update(f"Polling status endpoint every 10s...({attempt})")
            response = CLIENT.get(status_url)
            if response.status_code == httpx.codes.NOT_FOUND:
                not_found += 1
                if not_found <= _MAX_STATUS_NOT_FOUND:
                    console.print(
                        f"Status not stored yet (404); retry {not_found}/{_MAX_STATUS_NOT_FOUND}"
                    )
                    continue
            else:
                not_found = 0
            response.raise_for_status()
            body = cast(dict[str, Any], response.json())
            status = body["status"]

    return response, body, elapsed, uncertainty, False


def run_tests(
    query: Query, response: httpx.Response
) -> tuple[int, int, list[TestOutcome]]:
    """Run tests specified by query against the response.

    Returns the passed/failed counts and each test's structured outcome (the
    latter for the pipe report; the human view is printed as tests run).
    """
    passed = 0
    failed = 0
    outcomes: list[TestOutcome] = []

    for i, test in enumerate(query.tests or []):
        try:
            result = test.test(response)  # Returns report if failed otherwise None
            test_name = (
                test.__doc__.removesuffix(".") if test.__doc__ else test.__name__
            )

            message = ""
            if result.passed:
                message += "[green]✓[/]"
                passed += 1
            else:
                message += "[red]x[/]"
                failed += 1
            message += f" {i + 1}. {test_name}"

            report_long: Panel | None = None
            if result.info:
                if isinstance(result.info, str) and "\n" not in result.info:
                    message += f" ({result.info})"
                else:
                    details = (
                        result.info
                        if isinstance(result.info, str)
                        else "\n".join(result.info)
                    )
                    report_long = Panel(
                        Text(details),
                        title="details",
                        title_align="left",
                        expand=False,
                        box=box.SQUARE,
                        border_style="red",
                    )

            console.print(message)
            if report_long:
                console.print(report_long)

            outcomes.append(
                {"name": test_name, "passed": result.passed, "info": result.info}
            )

        except Exception as error:
            console.print(
                f"[red]![/] {i + 1}. {test.__name__}: An error occurred in this test: {error!r}"
            )
            maybe_print_traceback()
            failed += 1
            outcomes.append(
                {"name": test.__name__, "passed": False, "info": repr(error)}
            )

    return passed, failed, outcomes
