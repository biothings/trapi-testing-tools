from typing import Optional
import httpx
from trapi_testing_tools.tests import http

method = "POST"
endpoint = "/asyncquery"
body = {
    "message": {
        "query_graph": {
            "nodes": {
                "input": {
                    "categories": ["biolink:PhenotypicFeature"],
                    "ids": ["uuid:1"],
                    "member_ids": ["HP:0002098", "HP:0001252", "HP:0001250"],
                    "set_interpretation": "MANY",
                },
                "output": {"categories": ["biolink:Gene"]},
            },
            "edges": {
                "edge_0": {
                    "subject": "input",
                    "object": "output",
                    "predicates": ["biolink:genetically_associated_with"],
                    "knowledge_type": "inferred",
                }
            },
        }
    }
}

def not_implemented_error(response: httpx.Response) -> Optional[str]:
    body = response.json()
    if body["description"] != "NotImplementedError":
        return "Did not get NotImplementedError."

tests = [http.status(200), not_implemented_error]
