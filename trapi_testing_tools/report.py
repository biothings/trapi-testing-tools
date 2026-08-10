import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, NotRequired, TypedDict, cast

import httpx

# A parsed JSON response body, or the raw text when the body isn't JSON.
ResponseBody = dict[str, Any] | list[Any] | str | None

StepStatus = Literal["ok", "no_response", "timeout", "error"]


class TestOutcome(TypedDict):
    """One test's result within a step."""

    name: str
    passed: bool
    info: str | list[str] | None


class TestSummary(TypedDict):
    """A step's overall test outcome plus each ordered case."""

    passed: bool
    cases: list[TestOutcome]


class StepResult(TypedDict):
    """One HTTP request: a query, or one step of a multi-step query, and its tests."""

    target: str  # full URL queried, including endpoint
    method: str
    status: StepStatus
    http_status: int | None  # HTTP status code, or None if no response
    error: str | None  # message when status != "ok", else None
    passed: bool  # request ok AND every test passed
    elapsed_seconds: float
    tests: TestSummary
    response: NotRequired[ResponseBody]  # omittable by a future flag


class QueryResult(TypedDict):
    """One query file run against one environment; a `steps` list (len 1 for a singleton)."""

    type: Literal["singleton", "multi_step"]
    path: str  # repo-relative query file path
    env: str  # the environment this query ran against
    passed: bool  # every step passed
    error: str | None  # pre-run failure (import/parse/missing); else None
    elapsed_seconds: float
    steps: list[StepResult]


class RunReport(TypedDict):
    """The whole ``--pipe`` envelope for one ``tt test`` invocation.

    A query run against multiple environments appears once per environment in
    `queries` (each carrying its own `env`).
    """

    envs: list[str]  # environments run against, in order
    query_count: int  # number of query results (files x environments)
    passed: bool  # every query passed
    elapsed_seconds: float
    queries: list[QueryResult]


# ##### construction #####


@dataclass
class StepRun:
    """Internal result of running one HTTP request, before tests are applied."""

    response: httpx.Response | None
    status: StepStatus
    http_status: int | None
    error: str | None
    elapsed: float
    target: str
    method: str


def _response_body(response: httpx.Response | None) -> ResponseBody:
    """The parsed JSON body, or the raw text when it isn't JSON, or None."""
    if response is None:
        return None
    try:
        return cast(ResponseBody, response.json())
    except Exception:
        return response.text


def build_step(
    run: StepRun,
    step_passed: bool,
    tests_passed: bool,
    outcomes: list[TestOutcome] | None = None,
    include_response: bool = True,
) -> StepResult:
    """Assemble a `StepResult` from a completed step run and its test outcomes.

    ``include_response`` off omits the response body entirely (report-only mode).
    """
    status = run.status
    if run.response is None and status == "ok":
        status = "no_response"
    step: StepResult = {
        "target": run.target,
        "method": run.method,
        "status": status,
        "http_status": run.http_status,
        "error": run.error,
        "passed": step_passed,
        "elapsed_seconds": round(run.elapsed, 3),
        "tests": {"passed": tests_passed, "cases": outcomes or []},
    }
    if include_response:
        step["response"] = _response_body(run.response)
    return step


def build_query_result(  # noqa: PLR0913
    path: Path,
    env: str,
    steps: list[StepResult],
    passed: bool,
    elapsed: float,
    multi_step: bool,
) -> QueryResult:
    """Assemble a `QueryResult` for a query that ran (singleton or multi-step)."""
    return {
        "type": "multi_step" if multi_step else "singleton",
        "path": str(path),
        "env": env,
        "passed": passed,
        "error": None,
        "elapsed_seconds": round(elapsed, 3),
        "steps": steps,
    }


def pre_run_failure(file: Path, env: str, error: str) -> QueryResult:
    """A `QueryResult` for a file that couldn't be run (missing/import/parse)."""
    return {
        "type": "singleton",
        "path": str(file),
        "env": env,
        "passed": False,
        "error": error,
        "elapsed_seconds": 0.0,
        "steps": [],
    }


def emit_report(
    queries: list[QueryResult],
    envs: list[str],
    passed: bool,
    elapsed: float,
    report_only: bool,
) -> None:
    """Write the pipe output to stdout.

    A lone single-step query emits just its raw response body for basic piping.
    Otherwise emits the aggregate `RunReport` envelope. ``report_only`` always
    emits the envelope (there are no responses to pipe raw).
    """
    if (
        not report_only
        and len(queries) == 1
        and queries[0]["type"] == "singleton"
        and queries[0]["steps"]
    ):
        response = queries[0]["steps"][0].get("response")
        if response is not None:
            print(
                json.dumps(response, ensure_ascii=False)
                if isinstance(response, dict | list)
                else response
            )
        return

    report: RunReport = {
        "envs": envs,
        "query_count": len(queries),
        "passed": passed,
        "elapsed_seconds": round(elapsed, 3),
        "queries": queries,
    }
    print(json.dumps(report, ensure_ascii=False))
