from tests.battery import standard_battery_2_0
from tests.constraints import EdgesSatisfySources

# 2.0 constraints.sources ALLOW: every returned edge must cite an allowed infores
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
                            "behavior": "ALLOW",
                            "values": ["infores:ctd", "infores:disgenet"],
                        }
                    },
                }
            },
        }
    },
}
tests = [
    *standard_battery_2_0(),
    EdgesSatisfySources.expect("ALLOW", "infores:ctd", "infores:disgenet"),
]
