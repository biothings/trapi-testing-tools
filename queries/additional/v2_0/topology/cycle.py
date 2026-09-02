from tests.battery import standard_battery_2_0

trapi_version = "2.0"
method = "POST"
endpoint = "/query"
body = {
    "parameters": {"tiers": [1]},
    "message": {
        "query_graph": {
            "nodes": {
                "n0": {"categories": ["biolink:Gene"], "ids": ["NCBIGene:3778"]},
                "n1": {"categories": ["biolink:Disease"]},
                "n2": {"categories": ["biolink:Cell"]},
            },
            "edges": {
                "e01": {
                    "subject": "n0",
                    "object": "n1",
                    "predicates": ["biolink:related_to"],
                },
                "e02": {
                    "subject": "n0",
                    "object": "n2",
                    "predicates": ["biolink:related_to"],
                },
                "e03": {
                    "subject": "n1",
                    "object": "n2",
                    "predicates": ["biolink:related_to"],
                },
            },
        }
    },
}
tests = standard_battery_2_0()
