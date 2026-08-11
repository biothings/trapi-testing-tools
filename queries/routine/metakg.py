from tests import http, metakg

method = "GET"
endpoint = "/meta_knowledge_graph"
tests = [http.Status, metakg.NodeCount, metakg.EdgeCount]
