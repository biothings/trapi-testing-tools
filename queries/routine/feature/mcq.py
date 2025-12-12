from typing import override

import httpx

from tests import http
from tests.base_test import Test, TestResult

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


class TRAPINotImplementedError(Test):
    """response desc. is NotImplementedError."""

    @override
    @staticmethod
    def test(response: httpx.Response) -> TestResult:
        body = response.json()
        passed = body["description"] == "NotImplementedError"
        return TestResult(passed, body["description"] if not passed else None)


tests = [http.status(200), TRAPINotImplementedError]
