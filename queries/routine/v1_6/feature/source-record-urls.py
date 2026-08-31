from tests import kg
from tests.battery import standard_battery

method = "POST"
endpoint = "/query"
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
tests = [*standard_battery(), kg.SourceRecordURLs]
# jsonpath "$.message.knowledge_graph.edges[*].sources[0].source_record_urls" isString
