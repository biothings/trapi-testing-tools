from tests import http, kg, logs, results

method = "POST"
endpoint = "/query"
body = {
    "parameters": {"tiers": [1]},
    "submitter": "bte-dev-tester-manual",
    "message": {
        "query_graph": {
            "nodes": {
                "n0": {"categories": ["biolink:Gene"]},
                "n1": {
                    "categories": ["biolink:Disease"],
                    "ids": ["UMLS:C0011847", "MONDO:0005240"],
                },
            },
            "edges": {
                "e01": {
                    "subject": "n0",
                    "object": "n1",
                    "predicates": ["biolink:causes"],
                }
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
]
