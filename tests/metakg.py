def node_count(response):
    no_nodes = len(response.json()["nodes"].keys()) == 0
    if no_nodes:
        return "0 nodes."


def edge_count(response):
    no_edges = len(response.json()["edges"]) == 0
    if no_edges:
        return "0 edges"
