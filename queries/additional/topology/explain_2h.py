from tests import http, kg, logs, results

method = "POST"
endpoint = "/query"
body = {
    "parameters": {"tiers": [1]},
    "submitter": "trapi-testing-tools",
    "message": {
        "query_graph": {
            "nodes": {
                "n0": {"categories": ["biolink:Gene"], "ids": ["NCBIGene:55364"]},
                "n1": {"categories": ["biolink:Gene"]},
                "n2": {"categories": ["biolink:Disease"], "ids": ["MONDO:0019136"]},
            },
            "edges": {
                "e01": {
                    "subject": "n0",
                    "object": "n1",
                    "predicates": ["biolink:related_to"],
                },
                "e02": {
                    "subject": "n1",
                    "object": "n2",
                    "predicates": ["biolink:related_to"],
                },
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
]
