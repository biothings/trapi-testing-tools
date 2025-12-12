from tests import http, kg, logs, results

query_body = {
    "submitter": "bte-dev-tester-manual",
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
    dict(
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
    dict(
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
