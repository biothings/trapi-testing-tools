from trapi_testing_tools.tests import http, kg, results, logs

# Using nephrotic syndrome as an example
method = "POST"
endpoint = "/asyncquery"
body = {
    "submitter": "bte-dev-tester-manual",
    "message": {
        "query_graph": {
            "nodes": {
                "n02": {"categories": ["biolink:Disease"], "ids": ["MONDO:0015564"]},
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
    },
}
tests = [
    http.status(200),
    kg.node_count,
    kg.edge_count,
    results.result_count,
    logs.no_error_logs,
]
