from tests import http, kg, logs, results

method = "POST"
endpoint = "/query"
body = {
    "parameters": {"tiers": [1]},
    "submitter": "trapi-testing-tools",
    "message": {
        "query_graph": {
            "nodes": {
                "n0": {"categories": ["biolink:Gene"], "ids": ["NCBIGene:3778"]},
                "n1": {"categories": ["biolink:Pathway"]},
                "n2": {"categories": ["biolink:Cell"]},
                "n3": {"categories": ["biolink:PhenotypicFeature"]},
                "n4": {"categories": ["biolink:Disease"]},
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
                "e03": {
                    "subject": "n2",
                    "object": "n3",
                    "predicates": ["biolink:related_to"],
                },
                "e04": {
                    "subject": "n2",
                    "object": "n4",
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
