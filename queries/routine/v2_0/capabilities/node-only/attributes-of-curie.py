from tests import http, trapi

# 2.0 makes QueryGraph.edges optional: a node-only "attributes of this CURIE?" query
trapi_version = "2.0"
method = "POST"
endpoint = "/query"
body = {
    "submitter": "trapi-testing-tools",
    "message": {
        "query_graph": {
            "nodes": {
                "n0": {"ids": ["NCBIGene:3778"]},
            }
        }
    },
}
tests = [http.Status, trapi.Structural]
