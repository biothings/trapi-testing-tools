from tests import http, metakg

trapi_version = "2.0"
method = "GET"
endpoint = "/meta_knowledge_graph"
tests = [
    http.Status,
    metakg.NodeCount,
    metakg.EdgeCount,
    # split so sources (served) and KL/AT (not yet served) report as separate pass/fail lines
    metakg.MetaEdgesAdvertise.expect("sources"),
    metakg.MetaEdgesAdvertise.expect("knowledge_levels", "agent_types"),
]
