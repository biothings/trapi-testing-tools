from tests import http, metakg

method = "GET"
endpoint = "/team/Text Mining Provider/meta_knowledge_graph"
tests = [http.Status, metakg.NodeCount, metakg.EdgeCount]
