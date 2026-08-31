from tests.battery import standard_battery_2_0

# 2.0 pathfinder: unified query_graph with a single `paths` QPath (no edges).
trapi_version = "2.0"
method = "POST"
endpoint = "/asyncquery"
body = {
    "message": {
        "query_graph": {
            "nodes": {
                "n0": {"ids": ["CHEBI:31690"]},
                "n2": {"ids": ["MONDO:0004979"]},
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
    },
}
tests = standard_battery_2_0()
