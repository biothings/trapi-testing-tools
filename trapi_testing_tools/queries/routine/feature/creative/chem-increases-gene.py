from trapi_testing_tools.tests import http, kg, results, logs

# Using MMP9 as an example
method = "POST"
endpoint = "/asyncquery"
body = {
    "submitter": "bte-dev-tester-manual",
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
tests = [
    http.status(200),
    kg.node_count,
    kg.edge_count,
    results.result_count,
    logs.no_error_logs,
]
