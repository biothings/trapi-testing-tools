#!/usr/bin/env python3
import json
import sys

# Load response from pipe
response_str = ""
for line in sys.stdin:
    response_str += line
response: dict = json.loads(response_str)

# Do things
results: list = response["message"]["results"]
kg: dict = response["message"]["knowledge_graph"]
aux: dict = response["message"]["auxiliary_graphs"]

hierarchy: list = []

max_depth = 1
max_depth_result = 0


def pprint(obj: dict):
    print(json.dumps(obj, indent=2))


def create_edge_hierarchy(kedge_id: str, depth=1):
    global max_depth
    max_depth = max(depth, max_depth)
    if max_depth > 4:  # We don't want to see this happen
        exit(1)
    kedge = kg["edges"][kedge_id]
    support_graphs = next(
        (
            attribute
            for attribute in (kedge["attributes"] or [])
            if attribute["attribute_type_id"] == "biolink:support_graphs"
        ),
        {"value": []},
    )["value"]
    if not len(support_graphs):
        return kedge["subject"], kedge["predicate"], kedge["object"]

    hierarchy = {}
    for support_id in support_graphs:
        for id in aux[support_id]["edges"]:
            hierarchy[id] = create_edge_hierarchy(id, depth + 1)
    return hierarchy


bound_edge_ids = set()
for i, result in enumerate(results):
    h_result = {}
    hierarchy.append(h_result)
    for qedge_id, bindings in result["analyses"][0]["edge_bindings"].items():
        if qedge_id not in h_result:
            h_result[qedge_id] = {}
        for binding in bindings:
            kedge_id = binding["id"]
            prev_depth = max_depth
            h_result[qedge_id][kedge_id] = create_edge_hierarchy(kedge_id)
            if max_depth >= prev_depth:
                max_depth_result = i


print(
    json.dumps(
        {
            "max_depth": max_depth,
            "max_depth_result": max_depth_result,
            "hierarchy": hierarchy,
        }
    )
)
