from tests.battery import standard_battery

# 1.6 qualifier_constraints: SmallMolecule -affects(activity_or_abundance, increased)-> EGFR
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
                    "qualifier_constraints": [
                        {
                            "qualifier_set": [
                                {
                                    "qualifier_type_id": "biolink:object_aspect_qualifier",
                                    "qualifier_value": "activity_or_abundance",
                                },
                                {
                                    "qualifier_type_id": "biolink:object_direction_qualifier",
                                    "qualifier_value": "increased",
                                },
                            ]
                        }
                    ],
                }
            },
        }
    },
}
tests = standard_battery()
