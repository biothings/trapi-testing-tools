from trapi_testing_tools.tests import kg, results, logs, http

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
            kg.node_count,
            kg.edge_count,
            results.result_count,
            logs.no_error_logs,
        ],
    ),
    dict(
        method="POST",
        endpoint="/query",
        body=query_body,
        tests=[
            http.status(200),
            kg.node_count,
            kg.edge_count,
            results.result_count,
            logs.no_error_logs,
            logs.found_cache_log,
        ],
    ),
]
