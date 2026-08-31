from tests.battery import standard_battery_2_0

# 2.0 constraints.qualifiers: {type_id: value} pairs AND'd; SmallMolecule -affects-> EGFR
trapi_version = "2.0"
method = "POST"
endpoint = "/query"
body = {
    "submitter": "trapi-testing-tools",
    "message": {
        "query_graph": {
            "nodes": {
                "chem": {"categories": ["biolink:SmallMolecule"]},
                "gene": {"categories": ["biolink:Gene"], "ids": ["NCBIGene:1956"]},
            },
            "edges": {
                "e01": {
                    "subject": "chem",
                    "object": "gene",
                    "predicates": ["biolink:affects"],
                    "constraints": {
                        "qualifiers": [
                            {
                                "biolink:object_aspect_qualifier": "activity_or_abundance",
                                "biolink:object_direction_qualifier": "increased",
                            }
                        ]
                    },
                }
            },
        }
    },
}
tests = standard_battery_2_0()
