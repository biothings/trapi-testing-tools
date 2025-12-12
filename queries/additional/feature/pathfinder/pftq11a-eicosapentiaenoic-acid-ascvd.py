from tests import http, kg, logs, results

method = "POST"
endpoint = "/asyncquery"
body = {
    "message": {
        "query_graph": {
            "nodes": {
                "n0": {"ids": ["CHEBI:28364"]},
                "un": {"categories": ["biolink:NamedThing"]},
                "n2": {"ids": ["MONDO:0005311"]},
            },
            "edges": {
                "e0": {
                    "subject": "n0",
                    "object": "un",
                    "predicates": ["biolink:related_to"],
                    "knowledge_type": "inferred",
                },
                "e1": {
                    "subject": "un",
                    "object": "n2",
                    "predicates": ["biolink:related_to"],
                    "knowledge_type": "inferred",
                },
                "e2": {
                    "subject": "n0",
                    "object": "n2",
                    "predicates": ["biolink:related_to"],
                    "knowledge_type": "inferred",
                },
            },
        }
    }
}
tests = [
    http.status(200),
    kg.NodeCount,
    kg.EdgeCount,
    results.ResultCount,
    logs.NoErrorLogs,
]
