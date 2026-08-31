from tests.battery import standard_battery_2_0
from tests.constraints import EdgesSatisfyKLAT

# 2.0 constraints.knowledge_level DENY: no returned edge's knowledge_level may be denied
trapi_version = "2.0"
method = "POST"
endpoint = "/query"
body = {
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
                    "constraints": {
                        "knowledge_level": {
                            "behavior": "DENY",
                            "values": ["prediction"],
                        }
                    },
                }
            },
        }
    },
}
tests = [
    *standard_battery_2_0(),
    EdgesSatisfyKLAT.expect("knowledge_level", "DENY", "prediction"),
]
