from tests import logs
from tests.battery import standard_battery

method = "POST"
endpoint = "/query"
body = {
    "bypass_cache": True,
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
tests = [*standard_battery(), logs.CacheBypassLog, logs.NoCacheHits]
