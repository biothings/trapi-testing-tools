from trapi_testing_tools.tests import http, metakg

method = "GET"
endpoint = "/smartapi/8f08d1446e0bb9c2b323713ce83e2bd3/meta_knowledge_graph"
tests = [http.status(200), metakg.node_count, metakg.edge_count]
