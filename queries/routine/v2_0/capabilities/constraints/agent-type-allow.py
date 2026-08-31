from tests.battery import standard_battery_2_0
from tests.constraints import EdgesSatisfyKLAT

# 2.0 constraints.agent_type ALLOW; servers hierarchy-expand, so the expectation lists descendants too
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
                        "agent_type": {
                            "behavior": "ALLOW",
                            "values": ["automated_agent"],
                        }
                    },
                }
            },
        }
    },
}
tests = [
    *standard_battery_2_0(),
    EdgesSatisfyKLAT.expect(
        "agent_type",
        "ALLOW",
        "automated_agent",
        "data_analysis_pipeline",
        "computational_model",
        "text_mining_agent",
    ),
]
