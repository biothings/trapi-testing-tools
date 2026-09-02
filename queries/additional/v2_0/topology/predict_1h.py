from tests.battery import standard_battery_2_0

trapi_version = "2.0"
method = "POST"
endpoint = "/query"
body = {
    "parameters": {"tiers": [1], "timeout": -1, "bypass_cache": True},
    "message": {
        "query_graph": {
            "nodes": {
                "n0": {"categories": ["biolink:Gene"], "ids": ["NCBIGene:3778"]},
                "n1": {"categories": ["biolink:Disease"]},
            },
            "edges": {
                "e01": {
                    "subject": "n0",
                    "object": "n1",
                    "predicates": ["biolink:causes"],
                }
            },
        }
    },
}
tests = standard_battery_2_0()
