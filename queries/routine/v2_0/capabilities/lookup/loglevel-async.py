from tests import http, logs

trapi_version = "2.0"
method = "POST"
endpoint = "/asyncquery"
body = {
    "submitter": "trapi-testing-tools",
    "parameters": {"log_level": "INFO"},
    "message": {
        "query_graph": {
            "nodes": {
                "n0": {"categories": ["biolink:Gene"], "ids": ["NCBIGene:3778"]},
                "n1": {"categories": ["biolink:Gene"]},
            },
            "edges": {
                "e01": {
                    "subject": "n0",
                    "object": "n1",
                    "predicates": ["biolink:regulates"],
                }
            },
        }
    },
}
tests = [
    http.Status,
    logs.NoDebugLogs,
]
