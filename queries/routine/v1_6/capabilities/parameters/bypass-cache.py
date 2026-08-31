from tests.battery import standard_battery

# bypass_cache: a standard 1.6 body param (2.0 moves it under parameters)
method = "POST"
endpoint = "/query"
body = {
    "bypass_cache": True,
    "submitter": "trapi-testing-tools",
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
                    "predicates": ["biolink:related_to"],
                }
            },
        }
    },
}
tests = standard_battery()
