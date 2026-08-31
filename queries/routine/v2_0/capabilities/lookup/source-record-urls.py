from tests import kg
from tests.battery import standard_battery_2_0

# Erlotinib -affects-> EGFR: a result-bearing edge whose sources carry source_record_urls
trapi_version = "2.0"
method = "POST"
endpoint = "/query"
body = {
    "submitter": "trapi-testing-tools",
    "message": {
        "query_graph": {
            "nodes": {
                "n0": {"categories": ["biolink:SmallMolecule"], "ids": ["CHEBI:114785"]},
                "n1": {"categories": ["biolink:Gene"], "ids": ["NCBIGene:1956"]},
            },
            "edges": {
                "e01": {
                    "subject": "n0",
                    "object": "n1",
                    "predicates": ["biolink:affects"],
                }
            },
        }
    },
}
tests = [*standard_battery_2_0(), kg.SourceRecordURLs]
