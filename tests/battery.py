from tests import http, kg, logs, results, trapi
from tests.base_test import Test
from tests.params import composite


def standard_battery() -> list[type[Test]]:
    """A standard battery of tests for your typical lookup query.

    Status and the counts stay individual (they carry info on pass); the always-silent
    integrity checks are folded into one `composite` that only expands on failure.
    """
    return [
        http.Status,
        kg.NodeCount,
        kg.EdgeCount,
        results.ResultCount,
        composite(
            [
                trapi.Structural,
                kg.AllKGItemsBound,
                kg.BindingsResolveToKG,
                kg.NoOrphanAuxGraphs,
                kg.HasKLAT,
                kg.HasPrimaryKnowledgeSource,
                results.ResultsBindQueryNodes,
                results.ResultsBindQueryEdges,
                logs.NoErrorLogs,
            ],
            "integrity checks",
        ),
    ]


def standard_battery_2_0() -> list[type[Test]]:
    """The standard battery for a TRAPI 2.0 lookup query.

    `standard_battery` plus `trapi.Semantic` (the 2.0 null-freedom / minItems / `{ids}`
    binding-shape gate); every integrity check it folds is 2.0-valid unchanged.
    """
    return [
        http.Status,
        trapi.Structural,
        trapi.Semantic,
        kg.NodeCount,
        kg.EdgeCount,
        results.ResultCount,
        composite(
            [
                kg.AllKGItemsBound,
                kg.BindingsResolveToKG,
                kg.NoOrphanAuxGraphs,
                kg.HasKLAT,
                kg.HasPrimaryKnowledgeSource,
                results.ResultsBindQueryNodes,
                results.ResultsBindQueryEdges,
                logs.NoErrorLogs,
            ],
            "integrity checks",
        ),
    ]
