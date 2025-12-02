from tests import http

method = "POST"
endpoint = "/query"
body = {
    "submitter": "bte-dev-tester-manual",
    "message": {
        "query_graph": {
            "nodes": {
                "n0": {"categories": ["biolink:Gene"]},
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
                    "qualifier_constraints": [
                        {
                            "qualifier_set": [
                                {
                                    "qualifier_type_id": "biolink:fake",
                                    "qualifier_value": "value1",
                                },
                                {
                                    "qualifier_type_id": "biolink:fake",
                                    "qualifier_value": "value2",
                                },
                            ]
                        }
                    ],
                },
            },
        }
    },
}
tests = [
    http.status(422),
]
