from trapi_testing_tools.tests import http, kg, results, logs

method = "POST"
endpoint = "/smartapi/38e9e5169a72aee3659c9ddba956790d/query"
body = {
    "message": {
        "query_graph": {
            "nodes": {
                "n0": {"categories": ["biolink:Gene"], "ids": ["UniProtKB:Q08722"]},
                "n1": {"categories": ["biolink:SmallMolecule"]},
            },
            "edges": {
                "e01": {
                    "subject": "n0",
                    "object": "n1",
                    "predicates": ["biolink:physically_interacts_with"],
                }
            },
        }
    }
}
tests = [
    http.status(200),
    kg.node_count,
    kg.edge_count,
    kg.kl_at,
    results.result_count,
    logs.no_error_logs,
]
