from tests.battery import standard_battery_2_0

trapi_version = "2.0"
method = "POST"
endpoint = "/asyncquery"
body = {
    "message": {
        "query_graph": {
            "nodes": {
                "n0": {
                    "ids": ["PUBCHEM.COMPOUND:445154"],
                    "categories": ["biolink:ChemicalEntity"],
                },
                "n2": {"ids": ["NCBIGene:2739"], "categories": ["biolink:Gene"]},
            },
            "paths": {
                "p0": {
                    "subject": "n0",
                    "object": "n2",
                    "predicates": ["biolink:related_to"],
                    "knowledge_type": "inferred",
                    "constraints": [
                        {"required_intermediate_categories": ["biolink:Protein"]}
                    ],
                }
            },
        }
    }
}
tests = standard_battery_2_0()
