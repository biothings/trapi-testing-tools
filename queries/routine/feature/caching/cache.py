from tests import http, kg, logs, results
from trapi_testing_tools.types import Query

query_body = {
    "submitter": "trapi-testing-tools",
    "message": {
        "query_graph": {
            "edges": {"e01": {"subject": "n0", "object": "n1"}},
            "nodes": {
                "n0": {
                    "ids": ["MONDO:0019391"],
                    "categories": ["biolink:Disease"],
                },
                "n1": {"categories": ["biolink:Gene"]},
            },
        }
    },
}
steps = [
    Query(
        method="POST",
        endpoint="/query",
        body=query_body,
        tests=[
            http.status(200),
            kg.NodeCount,
            kg.EdgeCount,
            results.ResultCount,
            logs.NoErrorLogs,
        ],
    ),
    Query(
        method="POST",
        endpoint="/query",
        body=query_body,
        tests=[
            http.status(200),
            kg.NodeCount,
            kg.EdgeCount,
            results.ResultCount,
            logs.NoErrorLogs,
            logs.FoundCacheLog,
        ],
    ),
]
