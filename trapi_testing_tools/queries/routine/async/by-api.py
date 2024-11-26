from trapi_testing_tools.tests import http, kg, results, logs

method = "POST"
endpoint = "/smartapi/d22b657426375a5295e7da8a303b9893/asyncquery"
body = {
    "submitter": "bte-dev-tester-manual",
    "message": {
        "query_graph": {
            "nodes": {
                "n0": {"categories": ["biolink:Gene"], "ids": ["NCBIGene:1017"]},
                "n1": {"categories": ["biolink:Gene"]},
            },
            "edges": {
                "e01": {
                    "subject": "n0",
                    "object": "n1",
                    "predicates": ["biolink:related_to"],
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
    logs.log_one_api,
]
