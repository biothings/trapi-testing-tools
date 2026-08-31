from tests.battery import standard_battery_2_0
from tests.constraints import CollatedResultsUnique

# 2.0 COLLATE (gene, middle node): all matching genes fold into one result; results distinguished only by the non-gene nodes+edges
trapi_version = "2.0"
method = "POST"
endpoint = "/query"
body = {
    "submitter": "trapi-testing-tools",
    "message": {
        "query_graph": {
            "nodes": {
                "chemical": {
                    "categories": ["biolink:ChemicalEntity"],
                    "ids": ["CHEBI:6801"],
                },
                "gene": {
                    "categories": ["biolink:Gene"],
                    "set_interpretation": "COLLATE",
                },
                "disease": {
                    "categories": ["biolink:Disease"],
                    "ids": ["MONDO:0005148"],
                },
            },
            "edges": {
                "e0": {
                    "subject": "chemical",
                    "object": "gene",
                    "predicates": ["biolink:related_to"],
                },
                "e1": {
                    "subject": "gene",
                    "object": "disease",
                    "predicates": ["biolink:related_to"],
                },
            },
        }
    },
}
tests = [
    *standard_battery_2_0(),
    CollatedResultsUnique.expect("gene"),
]
