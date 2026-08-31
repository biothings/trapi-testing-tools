from tests.battery import standard_battery_2_0
from tests.constraints import EdgesSatisfyKLAT

# 2.0 constraints.knowledge_level ALLOW: every returned edge's knowledge_level must be allowed
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
                            "behavior": "ALLOW",
                            "values": ["knowledge_assertion"],
                        }
                    },
                }
            },
        }
    },
}
tests = [
    *standard_battery_2_0(),
    EdgesSatisfyKLAT.expect("knowledge_level", "ALLOW", "knowledge_assertion"),
]
