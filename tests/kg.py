import httpx


def node_count(response: httpx.Response) -> str | None:
    body = response.json()
    no_nodes = len(body["message"]["knowledge_graph"]["nodes"].keys()) == 0
    if no_nodes:
        return "0 nodes."


def edge_count(response: httpx.Response) -> str | None:
    body = response.json()
    no_edges = len(body["message"]["knowledge_graph"]["edges"].keys()) == 0
    if no_edges:
        return "0 edges"


def source_record_urls(response: httpx.Response) -> str | None:
    body = response.json()
    has_source_record_urls = next(
        (
            edge
            for edge in body["message"]["knowledge_graph"]["edges"].values()
            if len(
                [
                    source
                    for source in edge["sources"]
                    if source.get("source_record_urls", None) is not None
                ]
            )
            > 0
        ),
        False,
    )
    if not has_source_record_urls:
        return "No edge has source_record_urls"


def kl_at(response: httpx.Response) -> str | None:
    body = response.json()
    has_kl_at = next(
        (
            edge
            for edge in body["message"]["knowledge_graph"]["edges"].values()
            if len(
                [
                    attr
                    for attr in edge["attributes"]
                    if attr["attribute_type_id"]
                    in ["biolink:knowledge_level", "biolink:agent_type"]
                ]
            )
        ),
        False,
    )
    if not has_kl_at:
        return "No edge has knowledge level or agent type"
