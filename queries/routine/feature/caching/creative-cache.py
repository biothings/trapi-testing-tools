from tests import http, kg, logs, results

# Using nephrotic syndrome as an example
query_body = {
    "message": {
        "query_graph": {
            "nodes": {
                "n02": {"categories": ["biolink:Disease"], "ids": ["MONDO:0005377"]},
                "n01": {"categories": ["biolink:ChemicalEntity"]},
            },
            "edges": {
                "e01": {
                    "subject": "n01",
                    "object": "n02",
                    "predicates": ["biolink:treats"],
                    "knowledge_type": "inferred",
                }
            },
        }
    }
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
