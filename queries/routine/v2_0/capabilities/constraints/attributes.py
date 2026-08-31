from tests.battery import standard_battery_2_0

# 2.0 constraints.attributes: the old attribute_constraints (here z_score > 5)
trapi_version = "2.0"
method = "POST"
endpoint = "/query"
body = {
    "submitter": "trapi-testing-tools",
    "message": {
        "query_graph": {
            "nodes": {
                "n0": {"categories": ["biolink:Gene"], "ids": ["NCBIGene:3778"]},
                "n1": {"categories": ["biolink:Disease"]},
            },
            "edges": {
                "e01": {
                    "subject": "n0",
                    "object": "n1",
                    "predicates": ["biolink:related_to"],
                    "constraints": {
                        "attributes": [
                            {
                                "id": "biolink:z_score",
                                "operator": ">",
                                "value": 5,
                            }
                        ]
                    },
                }
            },
        }
    },
}
tests = standard_battery_2_0()
