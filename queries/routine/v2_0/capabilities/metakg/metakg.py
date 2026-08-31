from tests import http, metakg

trapi_version = "2.0"
method = "GET"
endpoint = "/meta_knowledge_graph"
tests = [http.Status, metakg.NodeCount, metakg.EdgeCount]
