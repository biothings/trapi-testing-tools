"""Introspect the runtime-resolved capability surface of an installation.

Backs `tt manifest`: assembles, from config + the filesystem plugin trees + the test
registry, the dynamic surface `--help` structurally can't show — resolved environments,
per-version analyses (with arg schemas), the query tree, battery contents, and the
effective config. Every collector returns plain JSON-serializable data; the command
layer only picks domains and serializes.
"""

import importlib
from collections import Counter
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from types import ModuleType
from typing import Any

from rich import box
from rich.console import Console
from rich.table import Table
from rich.text import Text
from typer.main import get_command

import queries as query_list
import tests as tests_pkg
import trapi_testing_tools
from analysis.base_analysis import ParametrizedAnalysis
from tests.base_test import Test
from tests.battery import standard_battery, standard_battery_2_0
from tests.params import CountTest
from trapi_testing_tools.commands.utils import discover_analyses
from trapi_testing_tools.config import CONFIG, DEFAULT_ENVS
from trapi_testing_tools.utils import ENVIRONMENT_MAPPING, IndentedBlock, parse_query

# highlight=False so rich doesn't auto-color numbers/brackets — colors come from markup.
console = Console(stderr=True, highlight=False)

VERSIONS = ("1.6", "2.0")

_PACKAGE_ROOT = Path(trapi_testing_tools.__path__[0]).parent
_QUERIES_ROOT = Path(query_list.__path__[0]).resolve()


def collect_environments() -> dict[str, Any]:
    """The resolved environment surface: every app.level with its URL and source.

    ``source`` marks each instance ``default`` (matches the hardcoded `DEFAULT_ENVS`) or
    ``config`` (added/overridden via env/.env/config.yaml). ``resolved`` is the flat
    ``app.level → url`` map ``-e`` looks up.
    """
    apps: dict[str, Any] = {}
    for app_name, instances in CONFIG.environments.items():
        defaults = DEFAULT_ENVS.get(app_name, {})
        apps[app_name] = {
            level: {
                "url": url,
                "source": "default" if url == defaults.get(level) else "config",
            }
            for level, url in instances.items()
        }

    return {"apps": apps, "resolved": dict(ENVIRONMENT_MAPPING)}


def collect_config() -> dict[str, Any]:
    """The effective (post-layering) config values a run actually uses."""
    return {
        "viewer": CONFIG.viewer,
        "submitter": CONFIG.submitter,
        "timeout": CONFIG.timeout,
        "callback": CONFIG.callback.model_dump(),
    }


def _jsonable(value: object) -> Any:
    """Coerce a param default to something JSON-serializable, stringifying the exotic."""
    if isinstance(value, str | int | float | bool | type(None)):
        return value
    return repr(value)


def _analysis_args(cls: type[ParametrizedAnalysis]) -> list[dict[str, Any]]:
    """The arg schema of a parametrized analysis, read off its Typer command's params."""
    command = get_command(cls.app)
    return [
        {
            "name": param.name,
            "opts": list(param.opts),
            "type": param.type.name,
            "required": bool(param.required),
            "default": _jsonable(param.default),
            "help": getattr(param, "help", None),
            "is_argument": param.param_type_name == "argument",
        }
        for param in command.params
    ]


def collect_analyses(version: str) -> list[dict[str, Any]]:
    """Discovered analyses for one TRAPI version, with arg schemas for parametrized ones."""
    analyses: list[dict[str, Any]] = []
    for name, cls in sorted(discover_analyses(version).items()):
        display = (cls.__doc__ or "").strip().removesuffix(".")
        parametrized = issubclass(cls, ParametrizedAnalysis)
        entry: dict[str, Any] = {
            "name": name,
            "display": display,
            "version": version,
            "parametrized": parametrized,
        }
        if parametrized:
            entry["args"] = _analysis_args(cls)
        analyses.append(entry)
    return analyses


def _test_label(test: type[Test]) -> str:
    """A test's display label: the docstring's first line, sans trailing period."""
    doc = (test.__doc__ or "").strip()
    return doc.splitlines()[0].removesuffix(".") if doc else test.__name__


def _describe_test(test: type[Test]) -> dict[str, Any]:
    """A battery entry's name/label, unfolding a composite's members recursively."""
    entry: dict[str, Any] = {"name": test.__name__, "label": _test_label(test)}
    members = getattr(test, "subtests", None)
    if members:
        entry["members"] = [_describe_test(member) for member in members]
    return entry


def discover_tests() -> list[dict[str, Any]]:
    """The full `tests/` library — concrete `Test` subclasses, keyed by module.

    The analogue of `discover_analyses`: query files attach these, so a query author needs
    to know what exists. Unlike analyses/queries, `tests/` isn't directory-split by TRAPI
    version, so this library is version-independent (the version dimension shows up in
    *which battery* uses a test, below). Abstract bases (`Test`, `CountTest`) and
    re-exported names are excluded; `parametrized` flags the ones with an `expect(...)`
    variant builder.
    """
    root = Path(tests_pkg.__path__[0])
    found: list[dict[str, Any]] = []
    for path in sorted(root.glob("*.py")):
        if path.stem in ("__init__", "base_test", "params"):
            continue
        module = importlib.import_module(f"tests.{path.stem}")
        for name, obj in vars(module).items():
            if (
                isinstance(obj, type)
                and issubclass(obj, Test)
                and obj not in (Test, CountTest)
                and obj.__module__ == module.__name__
                and not getattr(obj, "__abstractmethods__", None)
            ):
                found.append(
                    {
                        "name": name,
                        "module": path.stem,
                        "label": _test_label(obj),
                        "parametrized": hasattr(obj, "expect"),
                    }
                )
    return found


def collect_tests(version: str | None = None) -> dict[str, Any]:
    """The `tests/` library plus the standard batteries that bundle it.

    ``tests`` is the whole discoverable library; ``batteries`` maps each standard battery
    to its version + unfolded checks. A pinned ``version`` filters ``batteries`` to the
    matching one; the test library is always shown in full.
    """
    batteries: dict[str, Any] = {}
    if version in (None, "1.6"):
        batteries["standard_battery"] = {
            "version": "1.6",
            "checks": [_describe_test(test) for test in standard_battery()],
        }
    if version in (None, "2.0"):
        batteries["standard_battery_2_0"] = {
            "version": "2.0",
            "checks": [_describe_test(test) for test in standard_battery_2_0()],
        }
    return {"tests": discover_tests(), "batteries": batteries}


def _describe_query_file(path: Path) -> dict[str, Any]:
    """Location + shape of one query file (endpoint, steps, async, tests), importing it."""
    rel = path.resolve().relative_to(_QUERIES_ROOT)
    parts = rel.with_suffix("").parts
    version_index = next(
        (i for i, part in enumerate(parts) if part in ("v1_6", "v2_0")), None
    )
    group = parts[version_index + 1] if version_index is not None else None
    capability = (
        parts[version_index + 2]
        if group == "capabilities" and version_index is not None
        else None
    )

    entry: dict[str, Any] = {
        "path": str(rel.with_suffix("")),
        "set": parts[0],
        "group": group,
        "capability": capability,
    }

    try:
        import_path = ".".join(
            path.resolve().relative_to(_PACKAGE_ROOT).with_suffix("").parts
        )
        module: ModuleType = importlib.import_module(import_path)
        parsed = parse_query(module)
        entry["trapi_version"] = parsed[0].trapi_version if parsed else None
        entry["steps"] = len(parsed) if hasattr(module, "steps") else 1
        entry["methods"] = list(dict.fromkeys(query.method for query in parsed))
        entry["endpoints"] = list(dict.fromkeys(query.endpoint for query in parsed))
        entry["async"] = any("asyncquery" in (query.endpoint or "") for query in parsed)
        entry["tests"] = sorted(
            {test.__name__ for query in parsed for test in (query.tests or [])}
        )
    except Exception as error:
        entry["error"] = repr(error)
    return entry


def collect_queries(version: str) -> dict[str, Any]:
    """The query tree for one version: capabilities, profile→capability links, and files."""
    version_seg = f"v{version.replace('.', '_')}"
    routine = _QUERIES_ROOT / "routine" / version_seg

    capabilities: dict[str, int] = {}
    cap_dir = routine / "capabilities"
    if cap_dir.is_dir():
        for cap in sorted(p for p in cap_dir.iterdir() if p.is_dir()):
            capabilities[cap.name] = sum(
                1 for f in cap.glob("*.py") if f.stem != "__init__"
            )

    profiles: dict[str, list[str]] = {}
    prof_dir = routine / "profiles"
    if prof_dir.is_dir():
        for prof in sorted(p for p in prof_dir.iterdir() if p.is_dir()):
            profiles[prof.name] = sorted(
                link.resolve().name for link in prof.iterdir() if link.is_symlink()
            )

    files = [
        _describe_query_file(path)
        for path in sorted(_QUERIES_ROOT.rglob("*.py"))
        if version_seg in path.parts and path.stem != "__init__"
    ]

    return {"capabilities": capabilities, "profiles": profiles, "files": files}


def build_manifest(domain: str, version: str | None) -> dict[str, Any]:
    """Assemble the requested domain(s), scoped to ``version`` or keyed by both versions.

    ``domain`` is one of ``envs``/``analyses``/``queries``/``tests``/``config`` or
    ``all``. Version-split domains emit ``{version: …}`` when no version is pinned.
    """
    versions = [version] if version else list(VERSIONS)

    def by_version(collector: Any) -> Any:
        return collector(version) if version else {v: collector(v) for v in versions}

    manifest: dict[str, Any] = {}
    if domain in ("all", "envs"):
        manifest["environments"] = collect_environments()
    if domain in ("all", "config"):
        manifest["config"] = collect_config()
    if domain in ("all", "analyses"):
        manifest["analyses"] = by_version(collect_analyses)
    if domain in ("all", "queries"):
        manifest["queries"] = by_version(collect_queries)
    if domain in ("all", "tests"):
        # tests/ isn't version-split; `version` only filters which batteries show.
        manifest["tests"] = collect_tests(version)
    return manifest


# --- rich rendering (default, human-facing; `--raw`/piping emits the JSON above) ---


@contextmanager
def _block(header: str, close: str) -> Iterator[None]:
    """Frame a section: a ``┌`` header, a ``│`` gutter on its body, a ``└`` close."""
    console.print(Text("┌ ", style="rule.line") + Text.from_markup(header))
    console.push_render_hook(IndentedBlock())
    try:
        yield
    finally:
        console.pop_render_hook()
    console.print(f"└ {close}", style="rule.line", markup=True)


def _kv_table() -> Table:
    """A borderless two-plus-column table for gutter-framed key/value listings."""
    return Table(box=None, show_header=False, pad_edge=False, padding=(0, 2, 0, 0))


def _versioned(value: Any) -> list[tuple[str | None, Any]]:
    """Normalize a domain payload to ``[(version, payload), …]``.

    A version-pinned run yields one ``(None, payload)``; an unpinned version-split
    domain is a ``{version: payload}`` map, yielded as its items.
    """
    if isinstance(value, dict) and value and all(key in VERSIONS for key in value):
        return list(value.items())
    return [(None, value)]


def render_environments(data: dict[str, Any]) -> None:
    """Render the resolved environments as an app/level/URL/source table."""
    table = _kv_table()
    table.add_column(style="white")
    table.add_column(style="bright_black")
    table.add_column(overflow="fold")
    table.add_column(style="yellow")
    for app_name, instances in data["apps"].items():
        first = True
        for level, info in instances.items():
            source = "" if info["source"] == "default" else "config"
            table.add_row(app_name if first else "", level, info["url"], source)
            first = False

    with _block(
        "environments",
        f"{len(data['apps'])} apps · [bright_black]config = overridden via yaml/env[/]",
    ):
        console.print(table)


def render_config(data: dict[str, Any]) -> None:
    """Render the effective config as a flat key/value table (callback nested)."""
    table = _kv_table()
    table.add_column(style="white")
    table.add_column(overflow="fold")
    for key, value in data.items():
        if key == "callback":
            for sub_key, sub_value in value.items():
                table.add_row(f"callback.{sub_key}", str(sub_value))
        else:
            table.add_row(key, str(value))

    with _block("config", "[bright_black]effective (post-layering) values[/]"):
        console.print(table)


def _render_analyses(version: str | None, analyses: list[dict[str, Any]]) -> None:
    """Render one version's analyses, args indented under parametrized ones."""
    suffix = f" · {version}" if version else ""
    with _block(
        f"analyses{suffix} · [bright_black]{len(analyses)} found[/]",
        f"[bright_black]{len(analyses)} analyses[/]",
    ):
        for entry in analyses:
            tag = " [magenta](parametrized)[/]" if entry["parametrized"] else ""
            display = (
                f" · [bright_black]{entry['display']}[/]" if entry["display"] else ""
            )
            console.print(f"[white]{entry['name']}[/]{tag}{display}", markup=True)
            for arg in entry.get("args", []):
                opts = "/".join(arg["opts"])
                req = " [red](required)[/]" if arg["required"] else ""
                console.print(
                    f"    [cyan]{opts}[/] [bright_black]<{arg['type']}>[/]{req}  "
                    f"[bright_black]{arg['help'] or ''}[/]",
                    markup=True,
                )


def render_analyses(data: Any) -> None:
    """Render analyses across one or both versions."""
    for version, analyses in _versioned(data):
        _render_analyses(version, analyses)


def _trim_path(path: str) -> str:
    """Drop the redundant ``<set>/v<ver>/`` prefix; the block already scopes both."""
    parts = path.split("/")
    version_index = next(
        (i for i, part in enumerate(parts) if part in ("v1_6", "v2_0")), None
    )
    return "/".join(parts[version_index + 1 :]) if version_index is not None else path


def _files_table(files: list[dict[str, Any]]) -> Table:
    """A per-file detail table (only shown under ``--files``); method/steps stay in JSON."""
    table = Table(
        box=box.SIMPLE_HEAD,
        show_edge=False,
        pad_edge=False,
        header_style="bright_black",
    )
    table.add_column("path", overflow="fold", ratio=3)
    for column in ("grp/cap", "endpoint", "async", "tests"):
        table.add_column(column, overflow="fold")
    for entry in files:
        path = _trim_path(entry["path"])
        if "error" in entry:
            table.add_row(path, "[red]import error[/]", "", "", "")
            continue
        table.add_row(
            path,
            entry.get("capability") or entry.get("group") or "",
            ", ".join(entry.get("endpoints", [])),
            "async" if entry.get("async") else "",
            str(len(entry.get("tests", []))),
        )
    return table


def _render_queries(version: str | None, tree: dict[str, Any], *, files: bool) -> None:
    """Render one version's query tree: capability/profile summary, then file counts."""
    suffix = f" · {version}" if version else ""
    file_list = tree["files"]
    by_set = Counter(entry["set"] for entry in file_list)
    async_count = sum(1 for entry in file_list if entry.get("async"))
    errors = sum(1 for entry in file_list if "error" in entry)

    with _block(
        f"queries{suffix}",
        "[bright_black]file-level detail: --files (or --raw for JSON)[/]"
        if not files
        else f"[bright_black]{len(file_list)} files[/]",
    ):
        console.print("[white]capabilities[/]", markup=True)
        cap_table = _kv_table()
        cap_table.add_column(style="bright_black")
        cap_table.add_column(justify="right")
        for name, count in tree["capabilities"].items():
            cap_table.add_row(name, str(count))
        console.print(cap_table)

        console.print("[white]profiles[/]", markup=True)
        for name, caps in tree["profiles"].items():
            console.print(
                f"  [bright_black]{name}[/] → {', '.join(caps)} "
                f"[bright_black]({len(caps)})[/]",
                markup=True,
            )

        set_summary = " · ".join(f"{s}: {n}" for s, n in sorted(by_set.items()))
        error_note = f" · [red]{errors} import errors[/]" if errors else ""
        console.print(
            f"[white]files[/] [bright_black]· {len(file_list)} total · "
            f"{async_count} async · {set_summary}[/]{error_note}",
            markup=True,
        )

        if files:
            console.print(Text(""))
            console.print(_files_table(file_list))


def render_queries(data: Any, *, files: bool) -> None:
    """Render the query tree across one or both versions."""
    for version, tree in _versioned(data):
        _render_queries(version, tree, files=files)


def _battery_line(checks: list[dict[str, Any]]) -> str:
    """One-line battery membership: each check's label, composites counted."""
    parts = [
        f"{check['label']} ({len(check['members'])})"
        if check.get("members")
        else check["label"]
        for check in checks
    ]
    return ", ".join(parts)


def render_tests(data: dict[str, Any]) -> None:
    """Render the `tests/` library (by module), then the batteries."""
    tests = data["tests"]
    batteries = data["batteries"]
    by_module: dict[str, list[dict[str, Any]]] = {}
    for test in tests:
        by_module.setdefault(test["module"], []).append(test)

    with _block(
        f"tests · [bright_black]{len(tests)} tests[/]",
        f"[bright_black]{len(tests)} tests · {len(batteries)} batteries[/]",
    ):
        for module, entries in by_module.items():
            console.print(f"[white]{module}[/]", markup=True)
            for entry in entries:
                tag = " [magenta](parametrized)[/]" if entry["parametrized"] else ""
                console.print(
                    f"  • [white]{entry['name']}[/]{tag} · "
                    f"[bright_black]{entry['label']}[/]",
                    markup=True,
                )

        console.print("[white]batteries[/]", markup=True)
        for name, battery in batteries.items():
            console.print(
                f"  [cyan]{name}[/] [bright_black]({battery['version']})[/] · "
                f"[bright_black]{_battery_line(battery['checks'])}[/]",
                markup=True,
            )


def render_manifest(manifest: dict[str, Any], *, files: bool) -> None:
    """Render whichever domains are present as framed rich blocks to stderr."""
    if "environments" in manifest:
        render_environments(manifest["environments"])
    if "config" in manifest:
        render_config(manifest["config"])
    if "analyses" in manifest:
        render_analyses(manifest["analyses"])
    if "queries" in manifest:
        render_queries(manifest["queries"], files=files)
    if "tests" in manifest:
        render_tests(manifest["tests"])
