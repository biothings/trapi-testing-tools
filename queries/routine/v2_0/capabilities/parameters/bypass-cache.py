from tests.battery import standard_battery_2_0
from tests.constraints import ParametersEchoed

# 2.0 moves bypass_cache under `parameters`; the server MUST echo parameters in the Response.
trapi_version = "2.0"
method = "POST"
endpoint = "/query"
body = {
    "submitter": "trapi-testing-tools",
    "parameters": {"bypass_cache": True},
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
tests = [*standard_battery_2_0(), ParametersEchoed.expect(bypass_cache=True)]
