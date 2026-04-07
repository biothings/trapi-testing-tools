from typing import override

import httpx

from tests import http
from tests.base_test import Test, TestResult

method = "POST"
endpoint = "/team/lalala/query"
body = {
    "submitter": "trapi-testing-tools",
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


class QueryNotTraversableStatus(Test):
    """response status is QueryNotTraversable."""

    @override
    @staticmethod
    def test(response: httpx.Response) -> TestResult:
        body = response.json()
        passed = body["status"] == "QueryNotTraversable"
        return TestResult(passed, body["status"] if not passed else None)


tests = [http.status(400), QueryNotTraversableStatus]
