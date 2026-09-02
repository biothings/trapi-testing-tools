from tests.battery import standard_battery

method = "POST"
endpoint = "/asyncquery"
body = {
    "message": {
        "query_graph": {
            "nodes": {
                "n0": {"ids": ["NCBIGene:3458"]},
                "un": {"categories": ["biolink:NamedThing"]},
                "n2": {"ids": ["CHEBI:16828"]},
            },
            "edges": {
                "e0": {
                    "subject": "n0",
                    "object": "un",
                    "predicates": ["biolink:related_to"],
                    "knowledge_type": "inferred",
                },
                "e1": {
                    "subject": "un",
                    "object": "n2",
                    "predicates": ["biolink:related_to"],
                    "knowledge_type": "inferred",
                },
                "e2": {
                    "subject": "n0",
                    "object": "n2",
                    "predicates": ["biolink:related_to"],
                    "knowledge_type": "inferred",
                },
            },
        }
    }
}
tests = standard_battery()
