import json
import re
from typing import override

import httpx

from tests import trapi
from tests.base_test import Test, TestResult


class NoErrorLogs(Test):
    """no error logs."""

    @override
    @staticmethod
    def test(response: httpx.Response) -> TestResult:
        model = trapi.parse_or_fail(response)
        if isinstance(model, TestResult):
            return model
        error_logs = [log.message for log in model.logs if "ERROR" in (log.level or "")]
        return TestResult(
            len(error_logs) == 0, error_logs if len(error_logs) > 0 else None
        )


class NoDebugLogs(Test):
    """no debug logs."""

    @override
    @staticmethod
    def test(response: httpx.Response) -> TestResult:
        model = trapi.parse_or_fail(response)
        if isinstance(model, TestResult):
            return model
        debug_logs = [log.message for log in model.logs if "DEBUG" in (log.level or "")]
        return TestResult(
            len(debug_logs) == 0, debug_logs if len(debug_logs) > 0 else None
        )


class LogOneAPI(Test):
    """logs state 1 API used."""

    @override
    @staticmethod
    def test(response: httpx.Response) -> TestResult:
        model = trapi.parse_or_fail(response)
        if isinstance(model, TestResult):
            return model

        has_log = any("(1) unique API" in (log.message or "") for log in model.logs)
        return TestResult(
            has_log,
            "Missing log stating single unique API used" if not has_log else None,
        )


class MissingIDLog(Test):
    """logs state SmartAPI ID missing."""

    @override
    @staticmethod
    def test(response: httpx.Response) -> TestResult:
        model = trapi.parse_or_fail(response)
        if isinstance(model, TestResult):
            return model

        has_log = any(
            log.level == "ERROR"
            and re.match(
                r"Specified SmartAPI ID(.*) is either invalid or missing.",
                log.message or "",
            )
            for log in model.logs
        )
        return TestResult(
            has_log,
            "Missing log stating SmartAPI ID is invalid or missing"
            if not has_log
            else None,
        )


class FoundCacheLog(Test):
    """logs state cached qEdge found."""

    @override
    @staticmethod
    def test(response: httpx.Response) -> TestResult:
        model = trapi.parse_or_fail(response)
        if isinstance(model, TestResult):
            return model

        has_log = any(
            re.search(r"\([1-9][0-9]*\) cached qEdges", log.message or "")
            for log in model.logs
        )
        return TestResult(has_log, None if has_log else "No logs report cached qEdges.")


class CacheBypassLog(Test):
    """logs state cache bypassed."""

    @override
    @staticmethod
    def test(response: httpx.Response) -> TestResult:
        model = trapi.parse_or_fail(response)
        if isinstance(model, TestResult):
            return model

        has_log = any(
            "REDIS cache is not enabled." in (log.message or "") for log in model.logs
        )
        return TestResult(
            has_log, None if has_log else "No logs indicating cache bypass."
        )


class NoCacheHits(Test):
    """no cache hit logs."""

    @override
    @staticmethod
    def test(response: httpx.Response) -> TestResult:
        model = trapi.parse_or_fail(response)
        if isinstance(model, TestResult):
            return model

        cache_hits = [
            log
            for log in model.logs
            if re.search(r"\([1-9][0-9]*\) cached qEdges", log.message or "")
        ]

        message: str | None = None
        if len(cache_hits) > 0:
            message = json.dumps(
                {
                    "note": "Logs indicate cache hit.",
                    "logs": [log.to_dict() for log in cache_hits],
                },
                indent=2,
            )

        return TestResult(len(cache_hits) == 0, message)


class DryRunLog(Test):
    """logs indicate dry run."""

    @override
    @staticmethod
    def test(response: httpx.Response) -> TestResult:
        model = trapi.parse_or_fail(response)
        if isinstance(model, TestResult):
            return model
        has_log = any(
            "Running dryrun of query, no API calls will be performed. Actual query execution order may vary based on API responses received."
            in (log.message or "")
            for log in model.logs
        )

        return TestResult(has_log, "Missing dryrun log" if not has_log else None)
