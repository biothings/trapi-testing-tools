from tests.battery import standard_battery

method = "POST"
endpoint = "/query"
body = {
    "parameters": {"tiers": [0], "timeout": -1},
    "message": {
        "query_graph": {
            "nodes": {
                "n0": {"categories": ["biolink:Gene"]},
                "n1": {"categories": ["biolink:Gene"]},
                "n2": {"categories": ["biolink:Disease"], "ids": ["UMLS:C0011847"]},
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
                    "predicates": ["biolink:causes"],
                },
            },
        }
    },
}
tests = standard_battery()
