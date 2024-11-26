from typing import Optional
import httpx
from trapi_testing_tools.tests import http

method = "POST"
endpoint = "/team/lalala/query"
body = {
    "submitter": "bte-dev-tester-manual",
    "message": {
        "query_graph": {
            "nodes": {
                "n0": {"categories": ["biolink:Gene"], "ids": ["NCBIGene:3778"]},
                "n1": {"categories": ["biolink:Gene"]},
            },
            "edges": {
                "e01": {
                    "subject": "n0",
                    "object": "n1",
                    "predicates": ["biolink:regulates"],
                }
            },
        }
    },
}


def query_not_traversable_status(response: httpx.Response) -> Optional[str]:
    body = response.json()
    if body["status"] != "QueryNotTraversable":
        return "Response status is not QueryNotTraversable."


tests = [http.status(400), query_not_traversable_status]
