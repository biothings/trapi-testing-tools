---
name: trapi-testing
description: >
  Playbook for the trapi-testing-tools CLI (`tt`), used to exercise and analyze
  TRAPI services in the NCATS Translator ecosystem and to extend the tooling.
  Use when running query files (`tt test`), running analyses (`tt analyze`),
  retrieving ARS responses by PK (`tt pk`), checking service health (`tt ping`),
  resolving names/normalizing CURIEs (`tt norm`), emitting curl (`tt curl`), or
  authoring new query files, analyses, or response tests. Triggers on: TRAPI,
  `tt`, trapi-tools, query file, analysis, ARS PK, routine tests, Translator
  service, name resolution, node normalization, CURIE lookup.
license: MIT
---

# TRAPI testing tools

A CLI (`tt`, also `trapi-tools`) for exercising and analyzing TRAPI services in
the NCATS Translator ecosystem. Python 3.13, managed with `uv`. See the repo
`README.md` for full documentation; this skill is the task-oriented playbook.

## Setup

```bash
uv sync                     # install deps + create .venv
source .venv/bin/activate   # then use `tt ...` directly
# OR prefix every command with `uv run` (e.g. `uv run tt test ...`)
```

Before committing code changes, run `uv run task fixup` (lint:fix + format:fix +
`ty` typecheck + deptry). Individual tasks: `task lint`, `task format:fix`,
`task typecheck`.

## Terminology (three separate plugin systems)

- **Query** — a Python module describing an HTTP request (or a `steps` list of
  requests) to send to a service. Run by `tt test`.
- **Analysis** — transforms a parsed TRAPI response into JSON output. Run by
  `tt analyze`. Not pass/fail.
- **Test** — a `Test` subclass that inspects a response and returns a
  pass/fail `TestResult` (with optional info). Attached to queries and run
  alongside them. Tests do many kinds of checks, not only validation.

All three are discovered by filesystem convention + dynamic import — **no
registration**. Drop a file in the right directory following the base-class
contract and it is picked up.

## Using the CLI

Every command has `--help`; interactive fuzzy selection kicks in when required
arguments are omitted. Interactive/rich UI goes to **stderr**; only piped
payloads go to **stdout**, which is what makes the pipelines below work.

**Run queries** (`tt test`):
```bash
tt test queries/routine/v1_6 -d -e retriever.local  # a version's routine battery, stop on failures, local retriever
tt test queries/routine/v2_0/profiles/lookup -e retriever.ci  # one profile's queries (folder of symlinks)
tt test queries/my_query.py -e shepherd.bte.ci -e retriever.ci   # run against multiple environments
tt test                             # no args → interactively pick query file(s) + environment(s)
```
The routine set is split by TRAPI version (`queries/routine/v1_6/**`,
`queries/routine/v2_0/**`); under each version, queries live in
`capabilities/<capability>/` with `profiles/<profile>/` directories of symlinks
selecting the subset a component type runs. Pass a folder to run a whole battery —
folders expand recursively (symlinks included). `-d/--debug` pauses on
failing queries to view/save (and, when piping, keeps responses only for
failures). `-e` sets the environment(s) — repeatable (interactive picker is
multiselect); with multiple, each query runs against each sequentially (see
below). `tt test` exits non-zero if any query or test fails.

**Run analyses** (`tt analyze`) — input from `-f file` or piped stdin:
```bash
tt analyze -f response.json                       # interactively pick analyses
tt analyze -f response.json NodeFrequency         # named analyses
tt analyze --list                                 # list available analyses
tt analyze PathCount -f response.json -- --start NCBIGene:3778 --end MONDO:0000437
tt analyze PathCount -- --help                    # help for a parametrized analysis
```
Args after a literal `--` are forwarded to a parametrized analysis. When piping
input you **must** name analyses (interactive selection needs `-f`). Analyses are
split by TRAPI version (`analysis/v1_6/`, `analysis/v2_0/`); `--trapi <ver>`
(default `1.6`) scopes discovery and the parse version.

**Pipe between commands** (`-p/--pipe` emits JSON to stdout):
```bash
tt test queries/my_query.py -e retriever.ci -p plain | tt analyze NodeFrequency -p | jq
```
For `tt test`, `--pipe/-p` requires a mode: `-p plain` pipes just the **response body**
(a lone body bare, so it chains into `tt analyze`; several as a JSON array); `-p report`
emits one `RunReport` envelope (per-query/step status, tests, timing, size — no bodies);
`-p full` is that envelope with responses. `-d` with
`-p` keeps only failing responses. Multiple `-e` run every query against
every environment; the envelope's top-level `envs` and each query's `env`
identify which run is which.

**Other commands:**
```bash
tt pk <PK> [--ara <name>]     # drill an ARS PK down to one ARA's stored response
tt pk <PK> --trace/-t         # skip the drill-down; show the overall ARS trace + per-actor metadata (incl. merge counts)
tt pk <PK> --raw/-r           # after picking a child, skip TRAPI extraction; emit the raw ARS stored response
tt pk <PK> --triage/-T        # fetch EVERY ARA response; per-actor metadata + standard battery in a tt-test-style block
tt ping [app] [--all]         # check service instances are responsive
tt norm <name…>               # resolve name(s) → CURIEs (Name Resolver); table to stderr
tt norm -i <curie…>           # normalize CURIE(s) → canonical id/equivalents/category (Node Normalizer)
tt norm <name> -e prod -r     # pick maturity (default test), -r/--raw prints raw JSON to stdout for piping
tt metakg -s Gene -p affects -o Disease -e <env>  # does the env's /meta_knowledge_graph support this edge? (or pass query file(s))
tt curl <query> -e <env>      # print the query as a curl command
tt diff <LEFT> [RIGHT]        # TRAPI-aware, order-insensitive diff of two responses (RIGHT via stdin); TRAPI 1.6/2.0, auto-detected from schema_version or forced with --trapi-version
tt tunnel [start|stop]        # status/prewarm/stop the shared cloudflared callback daemon used for remote async callbacks
```
Output flags shared across commands: `-v/--view` / `-V/--no-view` (view opens
`CONFIG.viewer`, default `fx`), `-s/--save <path>` / `-S/--no-save`, `-p/--pipe`
(on `tt test`, `-p` requires a mode: `-p plain` = response body, `-p report` = report
without bodies, `-p full` = report with bodies).

**Automated / non-interactive use: always pass explicit output flags.** When
view/save flags are omitted they default to `prompt`, and the command blocks on
interactive "View response body?" / "Save response body?" confirmations that
stall a non-interactive session. Pass `-p` to pipe JSON to stdout, `-s <path>
-V` to save without viewing, or `-V -S` to suppress both output paths. Without a
TTY these prompts auto-skip to no-view/no-save, but explicit flags are clearer.
(For the same reason, always supply query/analysis file arguments and `-e <env>`
explicitly so the fuzzy selection prompts never open.)

## Environments

Selected with `-e <app>.<level>` (e.g. `shepherd.bte.ci`, `retriever.local`). The
bare `<level>` also works for the default app (`retriever`), so `-e ci` == `-e
retriever.ci`. Apps/levels come from `DEFAULT_ENVS` in `config.py`: `ars`,
`gandalf`, `retriever`, the four `shepherd.<component>` apps
(`shepherd.aragorn`/`.arax`/`.bte`/`.sipr`), plus `nameres`/`nodenorm` for `tt
norm`. `config.yaml` is a commented template by default; uncomment its
`environments:` block to add or override services, and change
`default_environment` there to shorten the `-e` you type most.

## Authoring a query

Drop a `.py` file under `queries/`. Put it under the version subdir of the
routine set (`queries/routine/v1_6/capabilities/<capability>/` or the `v2_0`
equivalent) to include it in that version's battery. A module-level
`trapi_version` global (`"1.6"` default, or `"2.0"`) selects which TOM model
namespace its tests parse/validate against — set `"2.0"` for 2.0-shaped bodies
(top-level `parameters`, QEdge `constraints`, COLLATE, …). Note `.gitignore`
tracks only `queries/routine` and `queries/additional` — files elsewhere under
`queries/` are local-only.

**Single request** — module-level globals (`method` defaults to `GET`;
`endpoint` is required; `params`/`headers`/`body`/`tests`/`trapi_version` optional):
```python
from tests.battery import standard_battery

method = "POST"
endpoint = "/query"
body = {
    "message": {"query_graph": {"nodes": {...}, "edges": {...}}},
}
tests = standard_battery()   # list of Test subclasses; see below
```

**Multiple related requests** — a `steps` list of `Query` objects (defined in
`trapi_testing_tools/types.py`):
```python
from trapi_testing_tools.types import Query
from tests import logs
from tests.battery import standard_battery

steps = [
    Query(method="POST", endpoint="/query", body=query_body, tests=standard_battery()),
    Query(method="POST", endpoint="/query", body=query_body,
          tests=[*standard_battery(), logs.FoundCacheLog]),
]
```
`body` may be a dict/list or a `translator_tom` (TOM) model — both are
serialized automatically. Endpoints containing `asyncquery` are run to
completion automatically: by default TTT **receives the callback** (a local
receiver for loopback/private targets, a shared cloudflared tunnel for remote
ones), falling back to **polling** when cloudflared is unavailable or the body
sets its own `callback`. `CONFIG.callback.mode` (`auto`/`direct`/`tunnel`/`poll`)
picks the strategy, overridable per run with `--callback-mode`/`--cb`; manage the
shared tunnel daemon with `tt tunnel`.

**Follow-up steps (thread data between requests)** — when a step depends on an
earlier step's response (async submit → poll, create → read, capture a returned
value and reuse it), make it a `FollowUp` instead of a plain `Query`. `FollowUp`
is a `Query` subclass (`trapi_testing_tools/types.py`) whose `build(previous,
history)` you implement to construct that step's concrete `Query` at run time.
`previous` is the immediately-prior `StepRecord` (`history[-1]`) and `history` is
every prior step's record (each carries the parsed response, test outcomes, and
status). Use `self.derive(**overrides)` to copy this instance's own fields and
change only the dynamic bits:
```python
from trapi_testing_tools.console import console
from trapi_testing_tools.types import FollowUp, Query

class SubmitThenPoll(FollowUp):
    def build(self, previous, history) -> Query:
        job_id = previous.response.json()["job_id"]
        console.print(f"polling job {job_id}")   # ambient, auto-styled commentary
        return self.derive(endpoint=f"/status/{job_id}", method="GET")

steps = [
    Query(method="POST", endpoint="/asyncquery", body=query_body),
    SubmitThenPoll(tests=standard_battery()),
]
```
Override `repeat(previous, history)` (default `False`) to run the same step
again — rebuilt from its own latest result as `previous` — until it returns
`False`; a natural fit for the poll loop above.

To log from `build` in step with the runner's output, print via the shared
`console` (`from trapi_testing_tools.console import console`) rather than a bare
`print` — `build`-time output is auto-styled comment-color to read as ambient
commentary.

For TOM-model bodies, `trapi_testing_tools/query_utils.py` has convenience
constructors: `one_hop(...)` builds a two-node/one-edge query from
category/id/predicate args; `from_qg(query_graph, ...)` wraps an existing
`QueryGraph`/`PathfinderQueryGraph`; and `load_json(path, model)` loads a JSON
file as a given TOM model (a bare query graph, a `Message`, or a full `Query`)
and reconstructs a full query body.

## Authoring an analysis

Drop a `.py` file under `analysis/` — in the version subdir it targets
(`analysis/v1_6/` or `analysis/v2_0/`; `base_analysis.py` is shared). The **class
docstring is the display name** (trailing period stripped). One file may declare
several analyses that share helpers (see `analysis/v1_6/path.py`).

**Argument-free** — subclass `Analysis`:
```python
from translator_tom import Response
from analysis.base_analysis import Analysis, AnalysisOutput

class NodeFrequency(Analysis):
    """node frequency across kg edges."""

    @staticmethod
    def analyze(response: Response) -> AnalysisOutput:
        ...   # return a JSON-serializable dict or list
```

**With arguments** — subclass `ParametrizedAnalysis` and attach a single-command
`typer.Typer` app. Read the response from `ctx.obj`, prompt for anything missing,
return the output. CLI args arrive after `--`:
```python
import typer
from translator_tom import Response
from analysis.base_analysis import AnalysisOutput, ParametrizedAnalysis

app = typer.Typer(add_completion=False)

@app.command(context_settings={"ignore_unknown_options": True, "allow_extra_args": True})
def run(ctx: typer.Context, start: str | None = None) -> AnalysisOutput:
    response: Response = ctx.obj
    ...   # prompt for `start` if None (respect stdin.isatty() for non-interactive)
    return {...}

class MyAnalysis(ParametrizedAnalysis):
    """my parametrized analysis."""

    app = app
```

## Authoring a test

Drop a `Test` subclass under `tests/`. Its static `test` receives the raw
`httpx.Response` and returns a `TestResult(passed, info)`. The **class docstring
names the test** (trailing period stripped). Bundle commonly used tests into
`tests/battery.py::standard_battery()`.

To work with the parsed TRAPI model instead of raw JSON, use the `translator_tom`
(TOM)-aware helpers in `tests/trapi.py`: `parse_or_fail` returns a TOM `Response`
(or `parse_metakg_or_fail` a `MetaKnowledgeGraph`), or a failed `TestResult` you
return early when the body isn't valid TRAPI. Parsing is memoized per response,
so calling it across a battery is cheap — this is the idiom every `tests/kg.py`
test uses.

```python
from typing import override
import httpx
from tests import trapi
from tests.base_test import Test, TestResult

class HasResults(Test):
    """message has results."""

    @override
    @staticmethod
    def test(response: httpx.Response) -> TestResult:
        model = trapi.parse_or_fail(response)
        if isinstance(model, TestResult):
            return model  # not valid TRAPI — fail with the parse error
        results = model.message.results_list
        return TestResult(passed=len(results) > 0, info=f"{len(results)} results")
```
Parameterized and combined tests come from `tests/params.py`: `bind` pre-applies
keyword args to make a `Test` variant — the `.expect` classmethods use it (e.g.
`http.Status.expect(404)`, `kg.EdgeCount.expect(50, "gte")`) — and `composite`
bundles several tests into one that stays silent until a sub-test fails (see
`standard_battery`'s "integrity checks"). Existing helpers live in `tests/`
(`http`, `kg`, `logs`, `results`, `metakg`, `params`, plus the TOM helpers in
`trapi`); reuse them before writing new ones.

## Work in progress — do not rely on

`tt harness` and `tt validate` are incomplete (harness still has TODO markers
and a debug `print`; validate is a stub). Don't build on them or point users at
them until they're finished. The `NCATSTranslator/Tests` cache machinery
(`cache_tests`/`select_tests` in `utils.py`) feeds the unfinished harness and is
likewise not wired up end-to-end.
