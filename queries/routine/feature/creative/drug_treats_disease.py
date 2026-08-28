from tests.battery import standard_battery

# Using nephrotic syndrome as an example
method = "POST"
endpoint = "/query"
body = {
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
tests = standard_battery()
