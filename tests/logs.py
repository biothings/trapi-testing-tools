import json
import re
from typing import override

import httpx

from tests.base_test import Test, TestResult


class NoErrorLogs(Test):
    """no error logs."""

    @override
    @staticmethod
    def test(response: httpx.Response) -> TestResult:
        body = response.json()
        error_logs = [log["message"] for log in body["logs"] if "ERROR" in log["level"]]
        return TestResult(
            len(error_logs) == 0, error_logs if len(error_logs) > 0 else None
        )


class NoDebugLogs(Test):
    """no debug logs."""

    @override
    @staticmethod
    def test(response: httpx.Response) -> TestResult:
        body = response.json()
        debug_logs = [log["message"] for log in body["logs"] if "DEBUG" in log["level"]]
        return TestResult(
            len(debug_logs) == 0, debug_logs if len(debug_logs) > 0 else None
        )


class LogOneAPI(Test):
    """logs state 1 API used."""

    @override
    @staticmethod
    def test(response: httpx.Response) -> TestResult:
        body = response.json()

        has_log = next(
            (log for log in body["logs"] if "(1) unique API" in log["message"]), False
        )
        return TestResult(
            has_log,
            "Missing log stating single unique API used" if not has_log else None,
        )


class MissingIDLog(Test):
    """logs state SmartAPI ID missing."""

    @override
    @staticmethod
    def test(response: httpx.Response) -> TestResult:
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
        return TestResult(
            has_log,
            "Missing log stating single unique API used" if not has_log else None,
        )


class FoundCacheLog(Test):
    """logs state cached qEdge found."""

    @override
    @staticmethod
    def test(response: httpx.Response) -> TestResult:
        body = response.json()

        has_log = next(
            (
                log
                for log in body["logs"]
                if re.search(r"\([1-9][0-9]*\) cached qEdges", log["message"])
            ),
            False,
        )
        return TestResult(has_log, "No logs report cached qEdges." if has_log else None)


class CacheBypassLog(Test):
    """logs state cache bypassed."""

    @override
    @staticmethod
    def test(response: httpx.Response) -> TestResult:
        body = response.json()

        has_log = next(
            (
                log
                for log in body["logs"]
                if "REDIS cache is not enabled." in log["message"]
            ),
            False,
        )
        return TestResult(
            has_log, "No logs indicating cache bypass." if has_log else None
        )


class NoCacheHits(Test):
    """no cache hit logs."""

    @override
    @staticmethod
    def test(response: httpx.Response) -> TestResult:
        body = response.json()

        cache_hits = [
            log
            for log in body["logs"]
            if re.search(r"\([1-9][0-9]*\) cached qEdges", log["message"])
        ]

        message: str | None = None
        if len(cache_hits) > 0:
            message = json.dumps(
                {"note": "Logs indicate cache hit.", "logs": cache_hits}, indent=2
            )

        return TestResult(len(cache_hits) == 0, message)


class DryRunLog(Test):
    """logs indicate dry run."""

    @override
    @staticmethod
    def test(response: httpx.Response) -> TestResult:
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

        return TestResult(has_log, "Missing dryrun log" if not has_log else None)
