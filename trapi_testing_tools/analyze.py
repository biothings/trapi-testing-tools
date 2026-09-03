import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import httpx
import typer
from rich.console import Console
from rich.table import Table
from rich.text import Text

from analysis.base_analysis import AnalysisClass, ParametrizedAnalysis
from tests import http
from tests.battery import standard_battery, standard_battery_2_0
from tests.kg import edge_klat, edge_primary_sources
from trapi_testing_tools.trapi_models import TrapiVersion, detect_version, models
from trapi_testing_tools.types import OutputModes
from trapi_testing_tools.utils import (
    IndentedBlock,
    handle_output,
    maybe_print_traceback,
    render_test_result,
    serialize_body,
)

console = Console(stderr=True)


def read_response_bytes(file: Path | None) -> tuple[bytes, str]:
    """Read raw response bytes from a file or stdin, returning them with a source label."""
    source = "stdin" if file is None else str(file)
    try:
        data = file.read_bytes() if file is not None else sys.stdin.buffer.read()
    except OSError as error:
        console.print(f"ERROR: could not read {source}: {error!r}", style="red")
        raise typer.Exit(1) from error

    if not data.strip():
        console.print(f"ERROR: no input read from {source}.", style="red")
        raise typer.Exit(1)

    return data, source


def parse_response(
    data: bytes, source: str, version: TrapiVersion | None = None
) -> Any:
    """Parse raw bytes into a TRAPI Response for the given (or active) TRAPI version."""
    try:
        return models(version).Response.from_json(data)
    except Exception as error:
        console.print(
            f"ERROR: {source} is not a valid TRAPI response: {error!r}", style="red"
        )
        raise typer.Exit(1) from error


def detect_response_version(data: bytes) -> TrapiVersion | None:
    """The supported TRAPI version a raw response's `schema_version` denotes, if determinable."""
    try:
        schema_version = json.loads(data).get("schema_version")
    except (ValueError, AttributeError):
        return None
    return detect_version(schema_version)


def load_response(file: Path | None, version: TrapiVersion | None = None) -> Any:
    """Load a TRAPI Response (for the given or active TRAPI version), from a file or stdin."""
    data, source = read_response_bytes(file)
    return parse_response(data, source, version)


def collect_info(model: Any, version: TrapiVersion, raw: bytes) -> dict[str, Any]:
    """Metadata and metrics for a parsed TRAPI response (also the pipe envelope body)."""
    top = json.loads(raw) if raw.strip() else {}
    message = model.message
    kg = message.knowledge_graph
    nodes = kg.nodes if kg else {}
    edges = kg.edges if kg else {}
    qg = message.query_graph

    kl_at: Counter[tuple[str | None, str | None]] = Counter()
    sources: Counter[str] = Counter()
    for edge in edges.values():
        kl_at[edge_klat(edge)] += 1
        sources.update(edge_primary_sources(edge))

    logs = model.logs or []
    level_counts = Counter((log.level or "UNKNOWN") for log in logs)

    return {
        "trapi_version": version,
        "schema_version": top.get("schema_version"),
        "biolink_version": top.get("biolink_version"),
        "counts": {
            "results": len(message.results or []),
            "nodes": len(nodes),
            "edges": len(edges),
            "aux_graphs": len(message.auxiliary_graphs_dict),
        },
        "query_graph": {
            "nodes": len(qg.nodes) if qg else 0,
            "edges": len(getattr(qg, "edges", None) or {}) if qg else 0,
            "paths": len(getattr(qg, "paths", None) or {}) if qg else 0,
        },
        "knowledge_level_agent_type": [
            {"knowledge_level": kl, "agent_type": at, "count": count}
            for (kl, at), count in kl_at.most_common()
        ],
        "primary_sources": [
            {"source": source, "count": count}
            for source, count in sources.most_common()
        ],
        "logs": {
            "counts": dict(level_counts),
            "errors": [log.message for log in logs if "ERROR" in (log.level or "")],
            "warnings": [log.message for log in logs if "WARNING" in (log.level or "")],
        },
    }


def run_info_battery(model: Any, version: TrapiVersion) -> list[dict[str, Any]]:
    """Run the version-appropriate standard battery (minus HTTP status) on a parsed model.

    HTTP status is meaningless for an already-captured response, so it's dropped (counts
    and the collapsed integrity `composite` stay); mirrors `analysis.*.battery`.
    """
    http_response = httpx.Response(200, content=model.to_json(as_str=False))
    battery = standard_battery_2_0() if version == "2.0" else standard_battery()

    results = list[dict[str, Any]]()
    for test in battery:
        if test is http.Status:
            continue
        name = test.__doc__.removesuffix(".") if test.__doc__ else test.__name__
        try:
            outcome = test.test(http_response)
            results.append(
                {"test": name, "passed": outcome.passed, "info": outcome.info}
            )
        except Exception as error:
            results.append({"test": name, "passed": False, "info": f"error: {error!r}"})
    return results


def _format_klat(klat: list[dict[str, Any]]) -> str:
    """One `kl / at (count)` entry per line for the metadata table."""
    return "\n".join(
        f"{item['knowledge_level'] or '—'} / {item['agent_type'] or '—'} ({item['count']})"
        for item in klat
    )


def _format_sources(sources: list[dict[str, Any]]) -> str:
    """One `source (count)` entry per line for the metadata table."""
    return "\n".join(f"{item['source']} ({item['count']})" for item in sources)


def render_summary(
    target: Console, info: dict[str, Any], battery: list[dict[str, Any]], source: str
) -> None:
    """Open the framed block and render the metadata table and battery ✓/x lines.

    Leaves the `IndentedBlock` hook pushed; the caller closes the block with
    `render_verdict` once any analysis/view interaction is done.
    """
    target.rule(Text("┌ ", style="rule.line") + source, align="left")
    target.push_render_hook(IndentedBlock())

    table = Table(box=None, show_header=False, pad_edge=False)
    table.add_column("Field", style="rule.line", justify="left")
    table.add_column("Value", overflow="fold")

    counts = info["counts"]
    qg = info["query_graph"]
    qg_desc = f"{qg['nodes']} nodes / {qg['edges']} edges"
    if qg["paths"]:
        qg_desc += f" / {qg['paths']} paths"

    table.add_row("TRAPI Version", str(info["trapi_version"]))
    table.add_row(
        "Schema / Biolink",
        f"{info['schema_version'] or '—'} / {info['biolink_version'] or '—'}",
    )
    table.add_row("Results", str(counts["results"]))
    table.add_row("KG Nodes / Edges", f"{counts['nodes']} / {counts['edges']}")
    table.add_row("Aux Graphs", str(counts["aux_graphs"]))
    table.add_row("Query Graph", qg_desc)
    table.add_row("KL / AT", _format_klat(info["knowledge_level_agent_type"]) or "—")
    table.add_row("Primary Sources", _format_sources(info["primary_sources"]) or "—")
    logs = info["logs"]
    log_desc = ", ".join(f"{level} {n}" for level, n in logs["counts"].items()) or "—"
    table.add_row("Logs", log_desc)

    target.print(table)
    target.print(Text(""))

    for i, item in enumerate(battery):
        render_test_result(target, i + 1, item["test"], item["passed"], item["info"])


def run_analyses_inline(  # noqa: PLR0913
    target: Console,
    model: Any,
    analyses: list[AnalysisClass],
    forwarded_args: list[str],
    output_modes: OutputModes,
    save_path: Path | None,
) -> None:
    """Run each analysis within the open block (no per-analysis frame), viewing/saving each."""
    view_mode, save_mode = output_modes
    multiple = len(analyses) > 1

    for cls in analyses:
        path = save_path
        if path is not None and multiple:
            path = path.with_name(f"{cls.__name__}_{path.name}")

        target.print(Text(""))
        target.print(Text(cls.__name__, style="rule.line"))

        try:
            if issubclass(cls, ParametrizedAnalysis):
                output = cls.run(model, forwarded_args)
            else:
                output = cls.analyze(model)
        except Exception as error:
            target.print(f"[red]Error:[/] {error!r}", markup=True)
            maybe_print_traceback()
            continue

        handle_output(
            serialize_body(output), view_mode, save_mode, path, subject="analysis"
        )


def render_verdict(target: Console, battery: list[dict[str, Any]]) -> None:
    """Close the framed block with the battery pass/fail verdict."""
    passed = sum(1 for item in battery if item["passed"])
    failed = len(battery) - passed
    verdict = "[green]✓ Passed[/]" if failed == 0 else f"[red]X Failed[/] {failed}"
    if failed and passed:
        verdict += f"[white] ─ [/][green]Passed[/] {passed}"

    target.pop_render_hook()
    target.print(f"└ {verdict}", style="rule.line", markup=True)
