from tests import http, kg, logs, results

method = "POST"
endpoint = "/query"
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
    kg.NodeCount,
    kg.EdgeCount,
    results.ResultCount,
    logs.NoErrorLogs,
    logs.CacheBypassLog,
    logs.NoCacheHits,
]
