from tests import kg
from tests.battery import standard_battery

method = "POST"
endpoint = "/smartapi/38e9e5169a72aee3659c9ddba956790d/query"
body = {
    "message": {
        "query_graph": {
            "nodes": {
                "n0": {"categories": ["biolink:Gene"], "ids": ["UniProtKB:Q08722"]},
                "n1": {"categories": ["biolink:SmallMolecule"]},
            },
            "edges": {
                "e01": {
                    "subject": "n0",
                    "object": "n1",
                    "predicates": ["biolink:physically_interacts_with"],
                }
            },
        }
    }
}
tests = [*standard_battery(), kg.HasKLAT]
