from tests import http, kg, logs, results
from tests.base_test import Test


def standard_battery() -> list[type[Test]]:
    """A standard battery of tests for your typical lookup query."""
    return [
        http.Status,
        kg.NodeCount,
        kg.EdgeCount,
        results.ResultCount,
        kg.AllKGItemsBound,
        kg.BindingsResolveToKG,
        logs.NoErrorLogs,
    ]
