from tests import logs
from tests.battery import standard_battery
from trapi_testing_tools.types import Query

query_body = {
    "submitter": "trapi-testing-tools",
    "message": {
        "query_graph": {
            "edges": {"e01": {"subject": "n0", "object": "n1"}},
            "nodes": {
                "n0": {"ids": ["MONDO:0019391"], "categories": ["biolink:Disease"]},
                "n1": {"categories": ["biolink:Gene"]},
            },
        }
    },
}
steps = [
    Query(
        method="POST",
        endpoint="/query",
        params=dict(caching=False),
        body=query_body,
        tests=standard_battery(),
    ),
    Query(
        method="POST",
        endpoint="/query",
        params=dict(caching=False),
        body=query_body,
        tests=[*standard_battery(), logs.NoCacheHits],
    ),
]
