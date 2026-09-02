from tests.battery import standard_battery_2_0

trapi_version = "2.0"
method = "POST"
endpoint = "/asyncquery"
body = {
    "message": {
        "query_graph": {
            "nodes": {"n0": {"ids": ["CHEBI:45713"]}, "n2": {"ids": ["NCBIGene:2739"]}},
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
