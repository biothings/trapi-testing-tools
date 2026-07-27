from tests import logs
from tests.battery import standard_battery

method = "POST"
endpoint = "/smartapi/d22b657426375a5295e7da8a303b9893/query"
body = {
    "submitter": "trapi-testing-tools",
    "message": {
        "query_graph": {
            "nodes": {
                "n0": {"categories": ["biolink:Gene"], "ids": ["NCBIGene:1017"]},
                "n1": {"categories": ["biolink:Gene"]},
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
tests = [*standard_battery(), logs.LogOneAPI]
