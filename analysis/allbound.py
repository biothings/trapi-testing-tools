#!/usr/bin/env python3
from pathlib import Path
from typing import Annotated

import orjson
import typer

app = typer.Typer(no_args_is_help=True)


@app.command(no_args_is_help=True)
def check_all_bound(
    file_path: Path, verbose: Annotated[bool, typer.Option("--verbose", "-v")] = False
):
    # Load response from arg
    with file_path.open() as file:
        response = orjson.loads(file.read())

    # Do things
    results: list = response["message"]["results"]
    kg: dict = response["message"]["knowledge_graph"]
    aux: dict = response["message"]["auxiliary_graphs"]

    check_missing_nodes(kg, verbose)
    check_missing_edges(results, kg, aux, verbose)


def check_missing_nodes(kg: dict, verbose=False):
    missing_nodes: list[str] = []
    for edge_id, edge in kg["edges"].items():
        if edge["subject"] not in kg["nodes"]:
            missing_nodes.append(edge["subject"])
        if edge["object"] not in kg["nodes"]:
            missing_nodes.append(edge["object"])

    if len(missing_nodes):
        print(f"{len(missing_nodes)} MISSING NODES{':' if verbose else ''}")
        if verbose:
            for node in missing_nodes:
                print(f"  {node}")
    else:
        print("NO MISSING NODES.")


def check_missing_edges(results: list[dict], kg: dict, aux: dict, verbose=False):
    existing_edges = set(kg["edges"].keys())
    used_edges = set[str]()
    for result in results:
        for analysis in result["analyses"]:
            for edge_bindings in analysis["edge_bindings"].values():
                for binding in edge_bindings:
                    used_edges.add(binding["id"])
    for aux_graph in aux.values():
        used_edges.update(aux_graph["edges"])
    if missing := used_edges - existing_edges:
        print(f"{len(missing)} MISSING EDGES{':' if verbose else ''}")
        if verbose:
            for edge in missing:
                print(f"  {edge}")


app()
