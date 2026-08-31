from tests import http

# multi-CURIE set input: set_interpretation MANY over member_ids
trapi_version = "2.0"
method = "POST"
endpoint = "/query"
body = {
    "submitter": "trapi-testing-tools",
    "message": {
        "query_graph": {
            "nodes": {
                "input": {
                    "categories": ["biolink:PhenotypicFeature"],
                    "ids": ["uuid:1"],
                    "member_ids": ["HP:0002098", "HP:0001252", "HP:0001250"],
                    "set_interpretation": "MANY",
                },
                "output": {"categories": ["biolink:Gene"]},
            },
            "edges": {
                "edge_0": {
                    "subject": "input",
                    "object": "output",
                    "predicates": ["biolink:genetically_associated_with"],
                }
            },
        }
    },
}
tests = [http.Status]
