from tests.battery import standard_battery_2_0

trapi_version = "2.0"
method = "POST"
endpoint = "/asyncquery"
body = {
    "message": {
        "query_graph": {
            "nodes": {
                "n0": {"ids": ["NCBIGene:54716"]},
                "n2": {"ids": ["MONDO:0100096"]},
            },
            "paths": {
                "p0": {
                    "subject": "n0",
                    "object": "n2",
                    "predicates": ["biolink:related_to"],
                    "knowledge_type": "inferred",
                }
            },
        }
    }
}
tests = standard_battery_2_0()
