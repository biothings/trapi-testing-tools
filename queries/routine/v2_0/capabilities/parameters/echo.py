from tests import http
from tests.constraints import ParametersEchoed

# 2.0: a server receiving a Query with `parameters` MUST echo them in its Response.
trapi_version = "2.0"
method = "POST"
endpoint = "/query"
body = {
    "submitter": "trapi-testing-tools",
    "parameters": {"log_level": "INFO", "bypass_cache": True, "timeout": 300},
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
tests = [http.Status, ParametersEchoed]
