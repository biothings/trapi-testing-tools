from trapi_testing_tools.tests import metakg, http

method = "GET"
endpoint = "/meta_knowledge_graph"
tests = [http.status(200), metakg.node_count, metakg.edge_count]
