from tests import http

# a malformed qualifier in the 2.0 constraints object should be rejected (422)
trapi_version = "2.0"
method = "POST"
endpoint = "/query"
body = {
    "submitter": "trapi-testing-tools",
    "message": {
        "query_graph": {
            "nodes": {
                "n0": {"categories": ["biolink:Gene"]},
                "n1": {"categories": ["biolink:Gene"]},
            },
            "edges": {
                "e01": {
                    "subject": "n0",
                    "object": "n1",
                    "predicates": ["biolink:related_to"],
                },
                "e02": {
                    "subject": "n0",
                    "object": "n1",
                    "predicates": ["biolink:related_to"],
                    "constraints": {
                        "qualifiers": [
                            {"biolink:fake": "value1"},
                        ]
                    },
                },
            },
        }
    },
}
tests = [
    http.Status.expect(422),
]
