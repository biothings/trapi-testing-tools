from tests.battery import standard_battery_2_0
from tests.constraints import ParametersEchoed

# 2.0 parameters may carry custom keys; the server MUST echo them
trapi_version = "2.0"
method = "POST"
endpoint = "/query"
body = {
    "submitter": "trapi-testing-tools",
    "parameters": {"custom_parameter": "example-value"},
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
tests = [
    *standard_battery_2_0(),
    ParametersEchoed.expect(custom_parameter="example-value"),
]
