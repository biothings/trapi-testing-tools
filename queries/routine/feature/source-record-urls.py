from tests import http, kg, logs, results

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
tests = [
    http.status(200),
    kg.NodeCount,
    kg.EdgeCount,
    kg.SourceRecordURLs,
    results.ResultCount,
    logs.NoErrorLogs,
]
# jsonpath "$.message.knowledge_graph.edges[*].sources[0].source_record_urls" isString
