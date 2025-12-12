from tests import http, metakg

method = "GET"
endpoint = "/meta_knowledge_graph"
tests = [http.status(200), metakg.NodeCount, metakg.EdgeCount]
