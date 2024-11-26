from trapi_testing_tools.tests import http, kg, results, logs

method = "POST"
endpoint = "/asyncquery"
body = {
    "submitter": "bte-dev-tester-manual",
    "bypass_cache": True,
    "message": {
        "query_graph": {
            "edges": {"e01": {"subject": "n0", "object": "n1"}},
            "nodes": {
                "n0": {"ids": ["MONDO:0019391"], "categories": ["biolink:Disease"]},
                "n1": {"categories": ["biolink:Gene"]},
            },
        }
    },
}
tests = [
    http.status(200),
    kg.node_count,
    kg.edge_count,
    results.result_count,
    logs.no_error_logs,
    logs.cache_bypass_log,
    logs.no_cache_hits,
]
