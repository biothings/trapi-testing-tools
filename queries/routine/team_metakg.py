from tests import http, metakg

method = "GET"
endpoint = "/team/Text Mining Provider/meta_knowledge_graph"
tests = [http.status(200), metakg.NodeCount, metakg.EdgeCount]
