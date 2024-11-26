from trapi_testing_tools.tests import http, kg, results, logs

method = "POST"
endpoint = "/asyncquery"
body = {
    "message": {
        "query_graph": {
            "nodes": {
                "n0": {
                    "ids": ["PUBCHEM.COMPOUND:3434975"],
                    "categories": ["biolink:Gene"],
                },
                "un": {"categories": ["biolink:Protein"]},
                "n2": {"ids": ["MONDO:0005575"], "categories": ["biolink:Disease"]},
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
    kg.node_count,
    kg.edge_count,
    results.result_count,
    logs.no_error_logs,
]
