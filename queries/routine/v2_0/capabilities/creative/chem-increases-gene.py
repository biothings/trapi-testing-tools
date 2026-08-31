from tests.battery import standard_battery_2_0

# Using MMP9 as an example
trapi_version = "2.0"
method = "POST"
endpoint = "/asyncquery"
body = {
    "submitter": "trapi-testing-tools",
    "message": {
        "query_graph": {
            "nodes": {
                "gene": {"categories": ["biolink:Gene"], "ids": ["NCBIGene:23162"]},
                "chemical": {"categories": ["biolink:ChemicalEntity"]},
            },
            "edges": {
                "t_edge": {
                    "object": "gene",
                    "subject": "chemical",
                    "predicates": ["biolink:affects"],
                    "knowledge_type": "inferred",
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
