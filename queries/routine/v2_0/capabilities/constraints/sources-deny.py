from tests.battery import standard_battery_2_0
from tests.constraints import EdgesSatisfySources

# 2.0 QEdge `constraints.sources` (DENY): no returned edge may cite the denied infores.
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
                        "sources": {
                            "behavior": "DENY",
                            "values": ["infores:semmeddb"],
                        }
                    },
                }
            },
        }
    },
}
tests = [
    *standard_battery_2_0(),
    EdgesSatisfySources.expect("DENY", "infores:semmeddb"),
]
