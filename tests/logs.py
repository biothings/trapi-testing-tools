import re

import httpx


def no_error_logs(response: httpx.Response) -> list[str] | None:
    body = response.json()
    error_logs = [log for log in body["logs"] if "ERROR" in log["level"]]
    if len(error_logs) > 0:
        return [log["message"] for log in error_logs]


def no_debug_logs(response: httpx.Response) -> list[str] | None:
    body = response.json()
    error_logs = [log for log in body["logs"] if "DEBUG" in log["level"]]
    if len(error_logs) > 0:
        return [log["message"] for log in error_logs]


def log_one_api(response: httpx.Response) -> str | None:
    body = response.json()
    has_log = next(
        (log for log in body["logs"] if "(1) unique API" in log["message"]), False
    )
    if not has_log:
        return "Missing log stating single unique API used"


def missing_id_log(response: httpx.Response) -> str | None:
    body = response.json()
    has_log = next(
        (
            log
            for log in body["logs"]
            if re.match(
                r"Specified SmartAPI ID(.*) is either invalid or missing.",
                log["message"],
            )
            and log["level"] == "ERROR"
        ),
        False,
    )
    if not has_log:
        return "Missing invalid smartapi error"


def found_cache_log(response: httpx.Response) -> str | None:
    body = response.json()
    has_log = next(
        (
            log
            for log in body["logs"]
            if re.search(r"\([1-9][0-9]*\) cached qEdges", log["message"])
        ),
        False,
    )
    if not has_log:
        return "No logs report cached qEdges."


def cache_bypass_log(response: httpx.Response) -> object | None:
    body = response.json()
    cache_disabled = next(
        (
            log
            for log in body["logs"]
            if "REDIS cache is not enabled." in log["message"]
        ),
        False,
    )
    if not cache_disabled:
        return "No logs indicating cache bypass."


def no_cache_hits(response: httpx.Response) -> object | None:
    body = response.json()
    cache_hits = [
        log
        for log in body["logs"]
        if re.search(r"\([1-9][0-9]*\) cached qEdges", log["message"])
    ]
    if len(cache_hits):
        return {"note": "Logs indicate cache hit.", "logs": cache_hits}


def dryrun_log(response: httpx.Response) -> str | None:
    body = response.json()
    has_log = next(
        (
            log
            for log in body["logs"]
            if "Running dryrun of query, no API calls will be performed. Actual query execution order may vary based on API responses received."
            in log["message"]
        ),
        False,
    )
    if not has_log:
        return "Missing dryrun log"
