from trapi_testing_tools.tests import http, kg, logs, results

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
