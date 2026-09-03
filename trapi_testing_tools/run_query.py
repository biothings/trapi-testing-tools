import importlib
import time
from dataclasses import dataclass, field, replace
from pathlib import Path
from types import ModuleType
from typing import Any, Literal, cast

import httpx
from rich.text import Text

import trapi_testing_tools
from trapi_testing_tools.analyze import (
    detect_response_version,
    parse_response,
    read_response_bytes,
)
from trapi_testing_tools.callback import (
    PLACEHOLDER_CALLBACK,
    CallbackSession,
    callback_session,
    make_synthetic_response,
)
from trapi_testing_tools.config import CONFIG
from trapi_testing_tools.diff import (
    colorize_report,
    diff_responses,
    render_report,
    render_text_report,
    render_verdict,
)
from trapi_testing_tools.report import (
    PipeMode,
    QueryResult,
    StepRecord,
    StepResult,
    StepRun,
    TestOutcome,
    build_query_result,
    build_record,
    build_step,
    emit_report,
    pre_run_failure,
)
from trapi_testing_tools.trapi_models import (
    DEFAULT_TRAPI_VERSION,
    TrapiVersion,
    use_version,
)
from trapi_testing_tools.types import FollowUp, OutputModes, Query
from trapi_testing_tools.utils import (
    IndentedBlock,
    comment_console,
    console,
    format_size,
    handle_output,
    inject_default_submitter,
    maybe_print_traceback,
    parse_query,
    render_test_result,
    serialize_body,
)

CLIENT = httpx.Client(
    follow_redirects=True, timeout=CONFIG.timeout if CONFIG.timeout >= 0 else None
)

# The status endpoint can 404 briefly before the server stores the (working) job.
_MAX_STATUS_NOT_FOUND = 3


def run_queries(  # noqa: PLR0913, PLR0912, PLR0915
    files: list[Path | ModuleType],
    targets: list[tuple[str, str]],
    output_modes: OutputModes,
    save_path: Path | None = None,
    on_fail: bool = False,
    pipe_mode: PipeMode | None = None,
    callback_mode: str | None = None,
    against: Path | None = None,
) -> bool:
    """Given a set of queries, run each against each target environment.

    ``targets`` is a list of ``(env_name, url)`` pairs; every query runs against
    every target, sequentially. Returns ``True`` only if every run passed. When
    piping (``pipe_mode`` set), stdout gets either the response body/bodies
    (`PipeMode.plain`) or one aggregate `RunReport` envelope (`report`/`full`).

    When ``against`` is given, the run's final response is structurally diffed against
    that baseline file: the summary goes to stderr, and (when piping) the plaintext diff
    report replaces the pipe payload on stdout.
    """
    collect = output_modes[0] == "pipe"  # only collect responses on pipe (save mem)
    report_queries: list[QueryResult] = []
    run_start = time.monotonic()

    against_bytes, against_source = (
        read_response_bytes(against) if against is not None else (b"", "")
    )
    last_final: httpx.Response | None = None
    last_version: TrapiVersion | None = None
    last_label = ""

    all_passed = True
    multiple = len(files) > 1 or len(targets) > 1
    with callback_session(callback_mode) as session:
        for path in files:
            package_root = Path(trapi_testing_tools.__path__[0]).parent
            # A pre-built module (e.g. `tt query`) skips the file discovery/import steps.
            if isinstance(path, ModuleType):
                query = path
                file = Path(cast(str, path.__file__)).resolve().relative_to(package_root)
            else:
                file = path.resolve().relative_to(package_root)
                if file.suffix != ".py":
                    console.print(
                        f"INFO: skipping {file} as it is not a python file",
                        style="italic bright_black",
                    )
                    continue
                if not file.exists():
                    console.print(
                        f"ERROR: {file} does not exist. Skipping...", style="red"
                    )
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
                            pre_run_failure(file, env, repr(error))
                            for env, _url in targets
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
                passed, result, (final_response, final_version) = manage_query(
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
                if final_response is not None:
                    last_final, last_version = final_response, final_version
                    last_label = f"{qualified} · {env}"

    if collect and against is None:
        emit_report(
            report_queries,
            [env for env, _url in targets],
            all_passed,
            time.monotonic() - run_start,
            pipe_mode or PipeMode.full,
        )

    if against is not None:
        # Offer to view/save the diff, but never reuse the response's save path (avoid clobber).
        diff_view_mode = "skip" if output_modes[0] == "skip" else "prompt"
        diff_save_mode = "skip" if output_modes[1] == "skip" else "prompt"
        _emit_diff(
            against_bytes,
            against_source,
            str(against),
            last_final,
            last_version,
            last_label,
            pipe_mode,
            diff_view_mode,
            diff_save_mode,
        )

    return all_passed


def _emit_diff(  # noqa: PLR0913
    against_bytes: bytes,
    against_source: str,
    against_name: str,
    response: httpx.Response | None,
    version: TrapiVersion | None,
    response_label: str,
    pipe_mode: PipeMode | None,
    view_mode: Literal["prompt", "skip", "every", "pipe"],
    save_mode: Literal["prompt", "skip", "every"],
) -> None:
    """Diff the run's final ``response`` against the baseline, per ``against`` semantics.

    The capped structural summary always prints to stderr; when piping, the full plaintext
    report is also written to stdout, overriding the normal pipe payload. Otherwise the
    report is passed to `handle_output`, offering to view (the full report) and/or save it.
    """
    if response is None:
        console.print("No response was produced to diff against.", style="yellow")
        return

    version = version or detect_response_version(against_bytes) or DEFAULT_TRAPI_VERSION
    left = parse_response(against_bytes, against_source, version)
    right = parse_response(response.content, "response", version)

    deltas = diff_responses(left, right, strict=True, version=version)
    render_report(deltas, strict=True)

    report = render_text_report(
        deltas, strict=True, left_name=against_name, right_name=response_label
    )
    if pipe_mode is not None:
        print(report)
    else:
        handle_output(
            report,
            view_mode,
            save_mode,
            None,
            subject="diff",
            view_transform=colorize_report,
        )

    render_verdict(deltas)


@dataclass
class _RunState:
    """Per-run output config plus state accumulated as each step runs."""

    collect: bool
    include_response: bool
    steps: list[StepResult] = field(default_factory=list)
    query_passed: bool = True
    total_passed: int = 0
    total_failed: int = 0
    any_tests: bool = False
    query_elapsed: float = 0.0
    final_response: httpx.Response | None = None
    trapi_version: TrapiVersion | None = None
    history: list[StepRecord] = field(default_factory=list)


def _run_step(
    step: Query,
    state: _RunState,
    url: str,
    session: CallbackSession | None,
) -> str | None:
    """Run one step, repeating if it's a repeating `FollowUp`, updating `state`.

    Returns a bail message if the step produced no response (the caller ends the
    query), else ``None``.
    """
    while True:
        # A FollowUp is built from prior results; a build error becomes a no-response step.
        query, run, bail_reason = _resolve_step(step, state.history, url)
        state.trapi_version = query.trapi_version
        if run is None:
            run = run_query(query, url, session)
        state.final_response = run.response
        state.query_elapsed += run.elapsed

        if run.response is None:
            state.query_passed = False
            if state.collect:
                state.steps.append(
                    build_step(
                        run,
                        step_passed=False,
                        tests_passed=True,
                        include_response=state.include_response,
                    )
                )
            return bail_reason

        step_ok = run.status == "ok"
        outcomes: list[TestOutcome] = []
        tests_passed = True
        if step_ok and query.tests is not None:
            state.any_tests = True
            with use_version(query.trapi_version):
                n_passed, n_failed, outcomes = run_tests(query, run.response)
            state.total_passed += n_passed
            state.total_failed += n_failed
            tests_passed = n_failed == 0

        step_passed = step_ok and tests_passed
        state.query_passed = state.query_passed and step_passed

        if state.collect:
            state.steps.append(
                build_step(
                    run,
                    step_passed,
                    tests_passed,
                    outcomes,
                    include_response=state.include_response,
                )
            )

        state.history.append(build_record(run, tests_passed, outcomes))

        # Loop only for a repeating FollowUp, rebuilding from its own last result.
        if not (isinstance(step, FollowUp) and _should_repeat(step, state.history)):
            return None


def manage_query(  # noqa: PLR0913
    query_module: ModuleType,
    url: str,
    env: str,
    output_modes: OutputModes,
    save_path: Path | None,
    on_fail: bool,
    pipe_mode: PipeMode | None,
    session: CallbackSession | None = None,
) -> tuple[bool, QueryResult | None, tuple[httpx.Response | None, TrapiVersion | None]]:
    """Interpret query as single or multiple and manage steps in running it.

    Returns whether the query (and any tests it defines) passed, a `QueryResult` when
    piping (for the aggregate report) else ``None``, and the run's final response with its
    TRAPI version (for ``--against`` diffing).
    """
    collect = output_modes[0] == "pipe"

    rel_path = Path(cast(str, query_module.__file__)).relative_to(
        Path(trapi_testing_tools.__path__[0]).parent
    )
    # Use rich text to create a section for this query's context
    console.rule(
        Text("┌ ", style="rule.line") + str(rel_path) + f" · {env}", align="left"
    )
    console.push_render_hook(IndentedBlock())

    queries = parse_query(query_module)
    state = _RunState(collect, include_response=pipe_mode is not PipeMode.report)

    for step in queries:
        bail_reason = _run_step(step, state, url, session)
        if bail_reason is not None:
            console.pop_render_hook()
            console.print(f"└ {bail_reason}", style="rule.line")
            result = (
                build_query_result(
                    rel_path,
                    env,
                    state.steps,
                    False,
                    state.query_elapsed,
                    len(queries) > 1,
                )
                if collect
                else None
            )
            return False, result, (state.final_response, state.trapi_version)

    console.pop_render_hook()

    # Output (non-pipe only; piping is aggregated into one report by run_queries)
    if not collect:
        _emit_output(
            state.final_response, output_modes, save_path, on_fail, state.query_passed
        )

    _print_verdict(
        state.query_passed, state.any_tests, state.total_passed, state.total_failed
    )

    # In debug mode, keep responses only for failing queries (the ones to inspect).
    if collect and on_fail and state.query_passed:
        for saved in state.steps:
            saved.pop("response", None)

    result = (
        build_query_result(
            rel_path,
            env,
            state.steps,
            state.query_passed,
            state.query_elapsed,
            len(queries) > 1,
        )
        if collect
        else None
    )
    return state.query_passed, result, (state.final_response, state.trapi_version)


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


def _build_followup(step: FollowUp, history: list[StepRecord]) -> Query:
    """Materialize a `FollowUp` into a concrete `Query` from prior step results.

    Mirrors `parse_query`'s tail on the built query (body serialization + submitter
    injection) so a FollowUp-built request behaves like a static one.
    """
    if not history:
        raise ValueError(
            "A FollowUp cannot be the first step (no prior result to build from)."
        )

    with comment_console():
        built = step.build(history[-1], history)

    return inject_default_submitter(replace(built, body=serialize_body(built.body)))


def _should_repeat(step: FollowUp, history: list[StepRecord]) -> bool:
    """Whether a `FollowUp` wants to run again; a raising `repeat` stops the loop."""
    try:
        with comment_console():
            return step.repeat(history[-1], history)
    except Exception as error:
        console.print(
            f"[red]FollowUp {type(step).__name__}.repeat failed:[/] {error!r}",
            markup=True,
        )
        maybe_print_traceback()
        return False


def _resolve_step(
    step: Query, history: list[StepRecord], url: str
) -> tuple[Query, StepRun | None, str]:
    """Resolve a step to its concrete `Query`, deferring `run` unless a FollowUp failed.

    Returns the query, a pre-built `StepRun` when a FollowUp's `build` raised (so the
    caller's no-response path reports it) else ``None``, and the bail message to show.
    """
    if not isinstance(step, FollowUp):
        return step, None, "No Response"
    try:
        return _build_followup(step, history), None, "No Response"
    except Exception as error:
        console.print(
            f"[red]FollowUp {type(step).__name__}.build failed:[/] {error!r}",
            markup=True,
        )
        maybe_print_traceback()
        run = StepRun(
            None,
            "error",
            None,
            repr(error),
            0.0,
            url + (step.endpoint or ""),
            step.method,
        )
        return step, run, f"FollowUp build failed: {error!r}"


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
        console.print(
            f"Callback: {PLACEHOLDER_CALLBACK} (placeholder; polling for result)"
        )
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

            if result.passed:
                passed += 1
            else:
                failed += 1
            render_test_result(console, i + 1, test_name, result.passed, result.info)

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
