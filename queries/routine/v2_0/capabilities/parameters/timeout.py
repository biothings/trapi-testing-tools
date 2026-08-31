from tests.battery import standard_battery_2_0
from tests.constraints import ParametersEchoed

# 2.0 adds `parameters.timeout` (seconds a client will wait); echoed in the Response.
trapi_version = "2.0"
method = "POST"
endpoint = "/query"
body = {
    "submitter": "trapi-testing-tools",
    "parameters": {"timeout": 300},
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
tests = [*standard_battery_2_0(), ParametersEchoed.expect(timeout=300)]
