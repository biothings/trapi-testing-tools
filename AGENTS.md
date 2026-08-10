# AGENTS.md

This file provides guidance to coding agents when working with code in this repository.

## What this is

A CLI (`tt`, also `trapi-tools`) for exercising and analyzing TRAPI services in the NCATS Translator ecosystem. It runs hand-written query files against configurable service environments, retrieves ARS responses by PK, and runs pluggable analyses over TRAPI responses. Python 3.13 only, managed with `uv`.

## Commands

```bash
uv sync                         # install deps + create .venv
source .venv/bin/activate       # or prefix everything below with `uv run`

uv run task lint                # ruff check .
uv run task lint:fix            # ruff check --fix .
uv run task format:fix          # ruff format .
uv run task typecheck           # ty check (the `ty` type checker, not mypy/pyright)
uv run task fixup               # lint:fix + format:fix + typecheck + deptry (run before committing)
uv run task yamllint            # lint YAML (config.yaml etc.)
```

There is **no pytest / unit-test suite.** The word "test" here means something else — see below. "Running tests" means running query files with `tt test`.

## The three-meanings-of-"test" gotcha

- **`tt test`** runs **query files** (HTTP requests to TRAPI services), not unit tests.
- **`tests/`** is a *library of TRAPI response validators* — subclasses of `Test` (`tests/base_test.py`) with a static `test(httpx.Response) -> TestResult`. Query files attach these to assert things about their response. `tests/battery.py::standard_battery()` bundles the common ones.
- **Analyses** (`analysis/`) transform a parsed response into JSON output; they are not pass/fail.

## Architecture

**CLI composition.** `trapi_testing_tools/main.py` builds one Typer app from per-command sub-apps in `trapi_testing_tools/commands/` (`test`, `analyze`, `pk`, `ping`, `curl`, `validate` — `validate` is a stub). `AliasGroup` enables `"test | t"`-style command aliases. Entry point `ttt` is a hack that injects `test` as argv[1].

**Three filesystem-convention plugin systems**, all discovered by `rglob` + dynamic `importlib` import (no registration):

1. **Queries** (`queries/`) — plain Python modules. Either module-level globals `method` / `endpoint` / `params` / `headers` / `body` / `tests`, **or** a `steps` list of `Query` objects (`trapi_testing_tools/types.py`) for multi-request flows. `parse_query` (`trapi_testing_tools/utils.py`) validates the shape and normalizes bodies. `queries/routine/**` is the set run by `tt test --all`. `tt test` positional args may be individual query files or folders (a folder runs every query within it, recursively; expanded in `set_queries`, `trapi_testing_tools/commands/utils.py`). Note `.gitignore` ignores `queries/*` except `routine` and `additional`, so ad-hoc queries under `queries/working/` are local-only.
2. **Analyses** (`analysis/`) — subclass `Analysis` (static `analyze(response)`) for argument-free, or `ParametrizedAnalysis` (holds a `typer.Typer` `app`; CLI args come after a `--` separator, response injected via `ctx.obj`). `discover_analyses` (`commands/utils.py`) finds concrete subclasses. **The class docstring is the display name** (final period stripped). See `analysis/path.py` for multiple analyses sharing helpers in one file.
3. **Response validators** (`tests/`) — see the gotcha section above.

**Configuration & environments.** `TTTConfig` (`config.py`, pydantic-settings) layers, in priority order: env vars (nested delimiter `__`) → `.env` → `config.yaml` → defaults. `DEFAULT_ENVS` (hardcoded ars/retriever/shepherd) is always merged in; `config.yaml` adds/overrides (bte, aragorn). `utils.py` flattens this into `ENVIRONMENT_MAPPING` keyed by `app.level` (e.g. `bte.ci`) **plus** bare `level` keys for `default_environment` — so with the default (`retriever`), `-e ci` resolves to `retriever.ci`.

**Output & piping (important).** All rich/interactive UI writes to **stderr**; only piped payloads go to **stdout**. This is what makes `tt test ... -p | tt analyze NAME -p | jq` work. `OutputModes = (view_mode, save_mode)` and the shared `handle_output` (`utils.py`) drive it: view opens `CONFIG.viewer` (default `fx`, falls back to `less` for non-JSON), save writes to a path (with multiple query files each response is saved under a path-qualified prefix, e.g. `routine.metakg_resp.json`), `-p/--pipe` prints JSON to stdout. Interactive selection (fuzzy prompts via InquirerPy) is disabled in pipe mode and requires a file/args instead; **without a TTY**, view/save (and traceback) prompts are skipped, defaulting to no-view/no-save. **`tt test` piping is aggregate** (`report.py`): a lone single-step query still pipes its bare response (so it chains into `tt analyze`), but multiple queries or a multi-step query emit one `RunReport` JSON envelope — per-query/per-step `status`/`http_status`/tests/timing/response — built only when piping. `-r/--report` implies `--pipe` and drops response bodies (run/test info only); `-d/--debug` with `--pipe` keeps responses only for failing queries. `tt test` exits non-zero if any query or test fails.

**Async queries.** `run_query` (`run_query.py`) detects `asyncquery` endpoints, polls `asyncquery_status` every 10s until done/timeout (`CONFIG.timeout`, default 300s), then GETs the final `response_url`.

**PK retrieval.** `tt pk` (`retrieve_by_pk.py`) fans out concurrently across all ARS instances to locate the PK, fetches the trace, prompts to pick an ARA child actor, and retrieves that ARA's stored TRAPI response. Metadata prints alongside the payload include a per-actor **merge count**, tallied by agent from the trace's `merged_versions_list` (a `repr`'d list parsed with `ast.literal_eval`, since a child's own copy is empty). `--trace/-t` skips the drill-down and outputs the whole trace with its per-actor metadata table; `--raw/-r` keeps the drill-down but skips `extract_response_payload`, emitting the raw ARS stored response instead of the TRAPI payload (`-t` takes precedence).

**translator_tom (TOM).** Query bodies may be raw dicts or TOM model objects (`serialize_body` normalizes them); analyses receive a parsed `translator_tom.Response`. TOM is imported lazily so raw-dict query authoring never loads it.

## Conventions

- Ruff is configured broadly (pydocstyle google convention, type-annotation rules, pathlib-over-os, etc.) with line length 88. Docstrings are required on public functions/classes.
- New analyses/queries/validators need no wiring — just drop a file in the right directory following the base-class contract.
