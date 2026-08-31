from tests import obi
from tests.battery import standard_battery

# OBI: a lookup on a parent term (diabetes mellitus) should also answer via subclass construct edges
method = "POST"
endpoint = "/query"
body = {
    "submitter": "trapi-testing-tools",
    "message": {
        "query_graph": {
            "nodes": {
                "drug": {"categories": ["biolink:ChemicalEntity"]},
                "disease": {
                    "categories": ["biolink:Disease"],
                    "ids": ["MONDO:0005015"],
                },
            },
            "edges": {
                "e01": {
                    "subject": "drug",
                    "object": "disease",
                    "predicates": ["biolink:treats"],
                }
            },
        }
    },
}
tests = [*standard_battery(), obi.HasOBIConstruct]
