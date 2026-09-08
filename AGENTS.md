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
- **`tests/`** is a *library of TRAPI response validators* — subclasses of `Test` (`tests/base_test.py`) with a static `test(httpx.Response) -> TestResult`. Query files attach these to assert things about their response. `tests/battery.py::standard_battery()` bundles the common ones; `standard_battery_2_0()` is the TRAPI 2.0 variant (adds `trapi.Structural`/`trapi.Semantic` and `kg.HasKLAT`). Version-specific 2.0 asserts live in `tests/constraints.py` (constraint honoring, `ParametersEchoed`, `CollatedIntoSingleResult`) and `tests/status.py` (`TrapiStatus`).
- **Analyses** (`analysis/`) transform a parsed response into JSON output; they are not pass/fail.

## Architecture

**Cross-cutting patterns.** Idioms shared across commands, defined once here; the per-command sections below note only their deviations.

- **Thin Typer layer + logic module.** Most commands split `commands/<x>.py` (Typer wiring / flag parsing) from `trapi_testing_tools/<x>.py` (HTTP + rich rendering), so `--raw`/`-r` can emit the fetched payload without rendering. Deviations: `diff.py` is a presentation layer over TOM's diff; `query.py` wraps `query_utils.one_hop`; `manifest.py` splits `collect_*` (dicts) from `render_*`.
- **Quick-output style.** `ping`, `norm`, `metakg`, `manifest`: the rich view renders to **stderr**; `--raw`/`-r` (for `manifest`, also a non-TTY stdout) prints the service's raw JSON to **stdout** for piping. No `handle_output`/view/save/`fx`.
- **TRAPI version resolution.** Over a *captured response* (`analyze`, `diff`, `analysis/` discovery) the version auto-detects from the response's `schema_version`; `--trapi-version/--tv` overrides; fallback is `1.6`. For *query files* the module's `trapi_version` global drives it instead (see Queries → TRAPI version dimension).
- **Synthetic `httpx.Response`.** A response arriving off the normal request path — streamed via `fetch.py`, received as an async callback, or rebuilt from an ARS-stored / captured body for a battery run — is rematerialized into a full `httpx.Response` so downstream tests/report/output see a uniform object.
- **Framed output block.** Interactive commands (`analyze`, `diff`, `pk`, `manifest`) frame output in a `┌`/`│`/`└` `IndentedBlock` on a stderr console; the closing `└` verdict/status prints *after* any view/save prompt so a prompt can't scroll or overwrite it.

**CLI composition.** One Typer app assembled from per-command sub-apps.

- `trapi_testing_tools/main.py` builds a single Typer app from the sub-apps in `trapi_testing_tools/commands/`: `test`, `query`, `analyze`, `diff`, `ping`, `norm`, `metakg`, `manifest`, `pk`, `curl`, `tunnel`.
- `AliasGroup` enables `"test | t"`-style command aliases.
- Entry point `ttt` is a hack that injects `test` as `argv[1]`.
- **`validate` and `harness` are unfinished and not registered on `main`.** Their `commands/` modules still exist (`validate` is an empty stub; `harness` carries TODOs and a debug `print`), but `main.py` deliberately doesn't `add_typer` them, so the CLI doesn't advertise them.

**`diff` command.** `tt diff [LEFT] [RIGHT]` is a TRAPI-aware, order-insensitive diff of two responses. `trapi_testing_tools/diff.py` is a **presentation/reporting layer over TOM's `diff`** — the order-insensitive, delta-returning diff engine lives in TOM (2.0); read TOM for the normalization / multiset-alignment / content-addressing internals.

- **Input resolution.** RIGHT reads stdin if omitted. With both files omitted in an interactive TTY, both are picked via fuzzy prompt from `responses/`; otherwise it errors.
- **Version dispatch (across TRAPI 1.6 and 2.0).**
  - `diff_responses(…, version=…)` calls `models(version).diff(...)`; the two versions' `diff`/`Delta` APIs are identical, so only dispatch differs.
  - `--trapi-version` forces the version. Omitted, `commands/diff.py` auto-detects each response's `schema_version` (helpers `detect_response_version`/`read_response_bytes`/`parse_response` in `analyze.py`) and warns when LEFT and RIGHT disagree.
  - Both responses are parsed as **one** version, so a real 1.x body vs a 2.0 body surfaces as a clean parse error.
- **Delta shape.** `models(version).diff(left, right, strict=…, normalize=True)` returns a flat list of typed `Delta(path, kind, left, right, locator)`. Kinds: `added` / `removed` / `changed` / **`reordered`** (a genuine reorder of an otherwise-identical list, `⇄` marker).
- **TOM wart filtered.** `diff_responses` drops a vacuous `changed` that TOM emits for *every* response-level extra field (`job_id`, `submitter`, …) without comparing values (dropped when `left == right`).
- **Two modes map to TOM's `strict`:**
  - **structural** — default, `strict=True`: every field-level change including attributes/provenance/score.
  - **identity** — `--identity`/`-i`, `strict=False`: only membership changes, ignoring attribute/provenance/**score**.
- **Rendering is this module's job.** `_classify` buckets each delta's `path` into a report section; three renderers consume the grouped deltas:
  - `render_text_report` — the **default**: compact git-diff-style plaintext (`--- / +++`, `@@ section counts @@` hunks, `+`/`-`/`~`/`⇄` lines); `--full` expands content inline as JSON blocks.
  - `render_report` — section-grouped rich summary to stderr, capped per section (`MAX_SHOWN`).
  - `build_report` — `--json`, machine-readable, always full, for `jq`/CI.
  - Emitted via `handle_output`. The plaintext view is ANSI-colored (`colorize_report`, piped through `less -R` via `handle_output`'s `view_transform` hook — save/pipe stay plain). The closing summary line lives in `render_verdict`, printed *after* the view/save interaction so a prompt can't scroll it off.
- **`tt test --against <file>` / `-a` reuses this diff.**
  - After a normal run it structurally diffs the run's **final** response (the last step's — for multiple queries/environments, the last produced response overall) against `<file>` as the baseline.
  - The rich summary goes to stderr; the plaintext report is offered to view/save (`_emit_diff` in `run_query.py`). When piping, the plaintext diff **replaces** the `-p` payload on stdout.
  - The baseline (left) is read once up front via `read_response_bytes`. The diff version is the run's `trapi_version` (falling back to the baseline's `schema_version`, then `1.6`). Persisted for `-R`.

**`analyze` command.** `tt analyze [FILE]` summarizes a captured TRAPI response and optionally runs analyses on it.

- **Logic** (`trapi_testing_tools/analyze.py`):
  - `collect_info` — metadata/metrics dict, also the pipe-envelope body.
  - `run_info_battery` — the standard battery **minus `http.Status`** (meaningless for a captured response), run against a rebuilt `httpx.Response`.
  - `render_summary` / `render_verdict` — open/close the framed `IndentedBlock`.
  - `run_analyses_inline` — runs the selected analyses.
- **Input.** A positional `FILE`, piped stdin, or (interactive TTY) a fuzzy pick from `responses/`. (Version resolves per Cross-cutting.)
- **Flow.**
  1. Render the metadata table + battery ✓/x lines in one gutter block.
  2. Select analyses: `-a NAME` (repeatable), else an interactive confirm+picker; `-A/--no-analysis` skips them and is mutually exclusive with `-a`.
  3. Run each analysis **inline in the same block** (no per-analysis frame) with view/save (`-v`/`-V`, `-s`/`-S`, prefixed by name for multiples).
  4. Offer to view the response body (**view-only, never saved**).
  5. Closing `└` verdict, printed last.
- **Exit code.** Exits non-zero when any battery check fails (the envelope/summary is emitted first).
- **`--pipe/-p`.** Emits **one JSON envelope** (`source` + metadata + `battery` + `analyses` keyed by class name); each analysis is guarded so one failure becomes `{"error": …}` rather than aborting the envelope.
- **Other flags.** `--list/-l` lists analyses; `-a NAME -- --help` shows a parametrized analysis' own args.
- **Gotcha — `FILE` has no `exists=` validator.** Click binds post-`--` tokens to the `FILE` positional, so on stdin input `file` is reset when it equals the first forwarded token. Because of that, bad paths error in `read_response_bytes` rather than at validation.

**`norm` command.** `tt norm [ITEMS…]` is a quick identifier lookup against Translator's SRI services — **name→CURIE** via Name Resolver (default) and **CURIE→canonical id/equivalents/category** via Node Normalizer (`--id`/`-i`).

- **Service calls** (quick-output style — see Cross-cutting; `normalize.py` splits HTTP from rendering so `--raw`/`-r` emits the raw payload):
  - name single → `/lookup` list.
  - name multiple → looped `/lookup` into a `{name: hits}` map (the Translator-hosted Name Resolver has no bulk endpoint).
  - id → `POST /get_normalized_nodes` yielding a `{curie: node|null}` map.
- **Input precedence.** Positional args → piped stdin (name = newline-split, id = whitespace-split) → interactive `InputPrompt`.
- **Name output.** Tables default to the top 5 rows with a `+N More` hint. `-n/--limit` unset fetches 10, shows 5; passing `-n N` fetches and shows N.
- **Id output.** A detail+equivalents view for one CURIE; a summary table for many (unmatched → "no match").
- **Environments.** The two services are `nameres`/`nodenorm` apps in `DEFAULT_ENVS` (per-maturity URLs from the SmartAPI registry; nodenorm's test/ci use the `nodenorm-es.<tier>.transltr.io` hosts). `-e/--environment` picks the maturity (default `test`); `_resolve_service_url` falls back to `prod` with a note if a maturity is absent.

**`query` command.** `tt query [OPTIONS]` (alias `q`) builds a **single-hop** TRAPI query inline from flags and runs it — no query file needed.

- **Layering.** `commands/query.py` is a thin wrapper over `query_utils.one_hop`. Node/edge flags map to `one_hop` args:
  - `--subject-category/--sc`, `--object-category/--oc`, `--subject-ids/--si`, `--object-ids/--oi`, `--predicate/--pred`, `--inferred`.
  - repeatable `--qualifier/-q type=value`.
  - repeatable `--param key=value` for extra body-level fields — each value JSON-parsed with a string fallback.
- **Synthesized module → full `tt test` parity.** It builds an **in-memory query module** carrying exactly the globals `parse_query` reads (`method`/`endpoint`/`body`/`tests`/`trapi_version`, plus a `__file__` under `queries/inline/` so `manage_query`'s `relative_to(<repo root>)` and the rule/report label work) and hands it to `run_queries` — whose `files` param accepts `list[Path | ModuleType]`, so a pre-built module skips the discovery/import steps while path items are unchanged. Inherited from `tt test`: repeatable `-e`, `--pipe/-p {plain,report,full}`, `--against/-a`, `--callback-mode/--cb`, view/save, and the rule/verdict UI.
- **Battery.** The version-appropriate standard battery runs by default (`standard_battery_2_0()` when `--trapi-version/--tv 2.0`, else `standard_battery()`); `--no-tests` sends without it.
- **Endpoint.** `--async` targets `/asyncquery` (else `/query`; method is always `POST`).
- **Constraints & persistence.** Requires at least one node constraint (else `Exit(1)`); no `-R`/last-run persistence (that's `test`-specific).
- **Inline name resolution.** Any `--subject-ids`/`--object-ids` value shaped `nameres:<name>` is resolved to its top Name Resolver CURIE before the query builds — `_resolve_nameres` reuses `normalize.resolve_names` (limit 1) and `norm._resolve_service_url("nameres", "test")` (the same `tt norm` lookup, `test` maturity, prod fallback), erroring on no match; literal CURIEs pass through untouched.

**`metakg` command.** `tt metakg` checks whether an environment's `/meta_knowledge_graph` advertises support for an edge.

- **Layers.** Standard split; fetch + rich rendering in `trapi_testing_tools/metakg.py`.
- **Two input modes:**
  - **Edge mode** — `-s/--subject`, `-p/--predicate`, `-o/--object` Biolink terms, plus repeatable `--qualifier TYPE:VALUE` and `--attribute` type CURIEs the edge must offer.
  - **File mode** — query file(s); checks each query's edges against the meta-KG.
- **Flags.** `-e/--environment` picks the target; `--trapi` the version (defaults per query file, else `1.6`).
- **Output.** Quick-output style (see Cross-cutting).

**`manifest` command.** `tt manifest [DOMAIN]` (alias `man`) introspects the **runtime-resolved capability surface** — the dynamic, config-/filesystem-/registry-derived map `--help` structurally can't show.

- **Layers.** `trapi_testing_tools/manifest.py` holds both the `collect_*`/`build_manifest` collectors (JSON-serializable dicts) and the `render_*`/`render_manifest` rich renderers.
- **Quick-output style (framed).** A framed rich view (`┌`/`│`/`└` blocks via `IndentedBlock`, on its own `highlight=False` stderr console) renders **by default**; the full **JSON surface goes to stdout** only with `--raw/-r` *or* when stdout isn't a TTY (piping) — so `tt manifest queries --raw | jq` works while a human gets a scannable map. `--compact/-c` selects one-line JSON.
- **Not a `--help` dump.** Static flag help is out of scope — this is the runtime surface, not a recursive help fan.
- **`DOMAIN`** (default `all`) is one of `envs`/`analyses`/`queries`/`tests`/`config`.
  - **Version-split domains** (`analyses`/`queries`/`tests`) are scoped by `--trapi-version/--tv` or, when omitted, keyed by both `1.6` and `2.0` (`build_manifest`'s `by_version`; the renderers' `_versioned` re-splits them). `envs`/`config` are version-independent.
- **Domains:**
  - **environments** — the resolved `ENVIRONMENT_MAPPING` (`apps` per-instance with `source` = `default` vs `config` override, plus the flat `resolved` map `-e` looks up).
  - **config** — the effective (post-layering) `viewer`/`submitter`/`timeout`/`test_repo`/`callback`.
  - **analyses** — `discover_analyses(version)` entries (name, docstring display, parametrized-or-not); parametrized ones also carry their **arg schema**, read off the Typer command's params via `typer.main.get_command` (collapsing the per-analysis `-- --help` fan).
  - **queries** — per version: `capabilities` (name→file count), `profiles` (name→the capability dirs it symlinks to), and `files` (each **imported + `parse_query`'d** for `trapi_version`/`methods`/`endpoints`/`steps`/`async`/`tests`, tagged with `set`/`group`/`capability`; import failures captured as `error` rather than aborting). The rich view **summarizes** (capability/profile lists + file counts by set/async); the full per-file table is opt-in via `--files/-f` (always present in JSON).
  - **tests** — the whole `tests/` **library** via `discover_tests` (the analogue of `discover_analyses`: every concrete `Test` subclass across the `tests/` modules, keyed by `module`, with a `parametrized` flag = has an `expect(...)` variant builder), **plus** the `batteries` that bundle them (`standard_battery`/`_2_0`, each with its version + `composite`-unfolded `checks`; composites expose a `subtests` attr for this). Unlike analyses/queries, `tests/` **isn't** directory-split by version, so the test library is version-independent and `--tv` only filters which battery shows.

**Three filesystem-convention plugin systems**, all discovered by `rglob` + dynamic `importlib` import (no registration):

1. **Queries** (`queries/`) — plain Python modules.
   - **Two shapes.** Either module-level globals `method` / `endpoint` / `params` / `headers` / `body` / `tests` / `trapi_version`, **or** a `steps` list of `Query` objects (`trapi_testing_tools/types.py`) for multi-request flows.
   - **`FollowUp` steps.** A `steps` entry may be a `FollowUp` — a `Query` subclass whose `build(previous, history)` you implement to construct that step's `Query` from earlier steps' results (each a `StepRecord`: response + test outcomes + status); use `self.derive(**overrides)` to copy the instance's fields and change only the dynamic bits. This threads data between steps (async submit → poll, create → read). `Query`/`FollowUp` are defined in `trapi_testing_tools/types.py`.
   - **`repeat`.** Override `repeat(previous, history)` (default `False`) to run the same step again — rebuilt from its own latest result as `previous` — until it returns `False`, e.g. poll until done.
   - **Logging from `build`.** To log in step with the runner's output, print via the shared console (`from trapi_testing_tools.console import console`), not a bare `print`; `build`-time output is auto-styled comment-color (like the re-run hint) to read as ambient commentary.
   - **`parse_query`** (`trapi_testing_tools/utils.py`) validates the shape and normalizes bodies. It **auto-injects a default `submitter`** (`inject_default_submitter`, value from `CONFIG.submitter`, default `trapi-testing-tools`; set to `""` to disable) into any query it detects as TRAPI — gated on *both* the endpoint being a TRAPI query path (`/query`/`/asyncquery`) *and* the body structurally being a TRAPI envelope (a `message` with a `query_graph`). So authors don't hand-write `submitter`; an author-set `submitter` is respected, never clobbered.
   - **Invoking.** `tt test` positional args are query files or folders (a folder runs every query within it, recursively; expanded in `set_queries`, `trapi_testing_tools/commands/utils.py`) — e.g. `tt test queries/routine/v2_0 -e retriever.ci`.
   - **Gotcha.** `.gitignore` ignores `queries/*` except `routine` and `additional`, so ad-hoc queries under `queries/working/` are local-only.
   - **TRAPI version dimension.**
     - A query file's `trapi_version` global (`"1.6"` default, or `"2.0"`) selects which TOM model namespace its tests parse/validate against — resolved centrally in `trapi_testing_tools/trapi_models.py` (a `current_trapi_version` ContextVar the runner binds per query; `models(v)` / `semantic_validate(v)`).
     - Author 2.0-shaped bodies (top-level `parameters`, QEdge `constraints`, COLLATE, etc.) and set `trapi_version = "2.0"`.
     - The routine set is split by version: `queries/routine/v1_6/**` and `queries/routine/v2_0/**`; run a version by pointing `tt test` at its folder.
     - The `additional` set (out-of-band `feature/pathfinder` and `topology` queries) is split the same way: `queries/additional/v1_6/**` and `queries/additional/v2_0/**`.
   - **Capability / profile organization.**
     - Under each version, query files live in `capabilities/<capability>/`. Both versions have `lookup`, `metakg`, `validation`, `constraints`, `parameters`, `set-input`, `subclassing`, `creative`, `pathfinder` (the last two are 2.0-and-ARA territory); `collate` and `node-only` exist only under `v2_0`.
     - `profiles/<profile>/` (`lookup`, `ara`, `minimal`) are **directories of symlinks to the capability dirs** a component type can run, so an owner selects one folder: `tt test queries/routine/v2_0/profiles/ara -e shepherd.aragorn.ci` vs `.../profiles/lookup -e retriever.ci` (everything except creative/pathfinder).
     - `set_queries` rglobs directory args with `recurse_symlinks=True` (Python 3.13+ skips symlinked dirs otherwise) and de-dups resolved paths (profiles overlap: `ara` ⊃ `lookup`).
     - Capabilities are the single source of truth; profile membership is a sensible default, not a contract (a service that can't do a capability just gets interpretable failures).
2. **Analyses** (`analysis/`) — subclass `Analysis` (static `analyze(response)`) for argument-free, or `ParametrizedAnalysis` (holds a `typer.Typer` `app`; CLI args come after a `--` separator, response injected via `ctx.obj`).
   - `discover_analyses(version)` (`commands/utils.py`) finds concrete subclasses.
   - **The class docstring is the display name** (final period stripped).
   - See `analysis/v1_6/path.py` for multiple analyses sharing helpers in one file.
   - **Split by TRAPI version** into `analysis/v1_6/` and `analysis/v2_0/` (mirroring the queries); `tt analyze` scopes discovery to the resolved version's subdir (version resolves per Cross-cutting) while binding the parse version, so same-named analyses across versions don't collide. `base_analysis.py` is shared.
3. **Response validators** (`tests/`) — see the gotcha section above.

**Configuration & environments.**

- **`TTTConfig`** (`config.py`, pydantic-settings) layers config in priority order: env vars (nested delimiter `__`) → `.env` → `config.yaml` → defaults.
- **`DEFAULT_ENVS`** is always merged in — hardcoded:
  - `ars`, `gandalf`, `retriever`;
  - the four `shepherd.<component>` apps: `shepherd.aragorn`, `.arax`, `.bte`, `.sipr`;
  - the `nameres`/`nodenorm` identifier services that `tt norm` uses.
- **`config.yaml`** is a commented template by default; uncommenting its `environments:` block adds/overrides services.
- **`ENVIRONMENT_MAPPING`** — `utils.py` flattens all of the above into this map, keyed by `app.level` (e.g. `shepherd.bte.ci`). This is what every `-e` resolves against.

**Output & piping (important).**

- **stderr vs stdout split.** All rich/interactive UI writes to **stderr**; only piped payloads go to **stdout**. This is what makes `tt test ... -p plain | tt analyze -a NAME -p | jq` work.
- **`OutputModes = (view_mode, save_mode)`** plus the shared `handle_output` (`utils.py`) drive output:
  - **view** opens `CONFIG.viewer` (default `fx`, falls back to `less` for non-JSON);
  - **save** writes to a path — with multiple query files/environments each response is saved under an env/path-qualified prefix, e.g. `retriever.dev.routine.metakg_resp.json`;
  - **`-p/--pipe`** prints JSON to stdout.
- **Interactive selection** (fuzzy prompts via InquirerPy) is disabled in pipe mode and requires a file/args instead. **Without a TTY**, view/save (and traceback) prompts are skipped, defaulting to no-view/no-save.
- **`tt test` piping shape is `--pipe/-p MODE`** (`report.py`, `PipeMode`; the flag requires a value):
  - **`-p plain`** — just the response body/bodies: a lone body bare (so it chains into `tt analyze`), several as a JSON array;
  - **`-p report`** — one aggregate `RunReport` JSON envelope (per-query/per-step `status`/`http_status`/tests/timing/`size_bytes`, no bodies);
  - **`-p full`** — that envelope *with* response bodies.
- **Aggregation & body inclusion.**
  - `elapsed_seconds`/`size_bytes` are aggregated at the query and run levels;
  - bodies are in/excluded per step at build (`include_response`); the envelope is built only when piping.
- **Per-step content `counts`.** Each step carries a content-shape `counts` (`results`/`nodes`/`edges`/`aux_graphs`, `null` when there's no response or it isn't valid TRAPI), so the envelope answers "did it return results, how many, what shape" without the body.
  - Computed by `_step_counts` (report.py `StepCounts`) off `analyze.content_counts` — the same helper `collect_info` uses.
  - Reuses the battery's memoized TOM parse (`tests.trapi.parse_or_fail`, same version), so no second full parse.
  - Computed only for `report`/`full` (not `plain`).
- **`-p report`/`-p full` compose with `-s <path>`.**
  - Piping still writes the run's final response body verbatim to disk (`_save_response_body`) and records its `saved_path` on the final step, so the envelope is a self-describing handle (verdict + shape + where the body is).
  - `set_output_modes` keeps an explicit `-s` under pipe (only a prompt-mode save is suppressed).
  - `-d/--debug` skips the save for passing queries.
- **`-e/--environment` is repeatable** (its interactive picker is multiselect): each query runs against each environment sequentially, yielding one `queries[]` entry per (query, environment) — each stamped with its `env`, all listed under the top-level `envs`.
- **`-d/--debug` with `--pipe`** keeps responses only for failing queries.
- **`tt test` exits non-zero** if any query or test fails.

**Repeat last test (`-R`).**

- **`tt test --repeat/-R`** replays the previous invocation.
- **Persistence.** After every `tt test` run the *resolved* invocation (queries as absolute paths, environment names, and the flags) is persisted as JSON to `PlatformDirs("trapi-testing-tools", "biothings").user_state_path / "last_test.json"` — see `last_run.py` (`save_last_test`/`load_last_test`).
  - Persisting *after* `set_queries`/`set_environment` captures interactive fuzzy-picks too.
- **Replay.** `-R` re-injects the remembered picks before resolution so no prompt fires, while any params typed on the current line **override** the remembered ones.
- **Override detection.** Uses `ctx.get_parameter_source(name) == COMMANDLINE` (the only `get_parameter_source` use in the repo).
  - **Exception:** `queries`, a variadic argument Click always reports as `COMMANDLINE` — for it, `queries is not None` is the "was it given?" signal.
- **Graceful fallback.** A missing snapshot dimension is left `None` so the normal prompt still fires; a wholly-missing snapshot with nothing typed is a friendly `Exit(1)`.

**HTTP fetch & live progress.** `fetch.py` is the shared live-progress request layer.

- **TTY-gated.** Live progress renders only on a TTY; off-TTY it's a no-op fallback, so piped stdout is never touched.
- **Three primitives:**
  - `fetch(client, method, url, **kwargs)` — sync single-bar path.
  - `stream_into(async_client, …, progress)` — async streaming primitive.
  - `live_rows(rows)` — stacks N `FetchProgress` rows under one `Live` for a concurrent multi-bar.
- **Invariant:** all three rebuild a fully-materialized `httpx.Response` (the synthetic-Response pattern in Cross-cutting).
- **Gotcha — decode exactly once.** They stream `iter_raw()` (undecoded wire bytes) and keep the original headers, so a `Content-Encoding: gzip` body decodes exactly once. Accumulating decoded `iter_bytes()` under the original gzip header double-decodes (`zlib` "incorrect header check").
- **Adopters:** `run_query` (main + async final-response GET), `metakg.fetch_metakg`, `retrieve_by_pk` (`get_ars_ara_response` single-bar; `_fetch_all_actor_responses` multi-bar for `pk --triage`), and the direct async-callback receiver (`CallbackReceiver.wait`/`_read_body` drive an inbound `Receiving callback...` bar; the tunnel path stays a spinner).
- **Not adopted** where a bar is wrong: disk-streamed downloads, status polls, quick-output lookups, concurrent `ping`.

**Async queries.** `run_query` (`run_query.py`) detects `asyncquery` endpoints and, by default, **receives the callback directly**.

- **Direct-receive default.** `callback.py` stands up an ephemeral local HTTP receiver, injects a per-query `callback` URL into the request body (via `dataclasses.replace`), then blocks until the service POSTs its response, which is wrapped as a synthetic `httpx.Response` (see Cross-cutting).
  - **Injection is gated:** the `callback` URL is injected **only** when the body has no callback of its own — an author-set `callback` is respected and **forces the poll path**.
- **Mode selection.** `CONFIG.callback.mode` (`auto`/`direct`/`tunnel`/`poll`, overridable per-run with `--callback-mode`/`--cb`) picks reachability:
  - **`auto`** — direct `127.0.0.1` callback for loopback/private targets (`_is_local_target`); a **cloudflared quick tunnel** for remote ones.
  - **`direct`** — a per-run local receiver (in-process `wait`).
  - **`tunnel`** — a detached, **global** daemon (`callback_daemon.py`, spawned via `python -m`) that holds the receiver + tunnel and is **shared by all `tt test` runs on the machine**. A single JSON state file (`tunnel.json`, in the platform state dir) is the discovery/reuse handle, so one tunnel is created and reused, not one per run.
    - The daemon has no owning shell: it persists in the background and reaps itself after an idle period (default 1800s) or on `tt tunnel stop`.
    - The `tt test` process awaits daemon callbacks by long-polling the daemon's local `GET /result/{token}`.
  - **`poll`** — the legacy fallback path (see below).
- **`tt tunnel` control.** Shows status (and, on a TTY, prompts to start/stop); `tt tunnel start` prewarms it, `tt tunnel stop` kills it. `start` is handy on TLS-intercepting networks to create the tunnel *before* connecting a VPN (a tunnel established off-VPN survives VPN activation).
- **Caveat — the daemon is global and *not* version-keyed** (matters when hacking on TTT across branches):
  - Whichever run starts it first runs it with that checkout's code; a concurrent run on a branch with a divergent callback/receiver protocol will reuse that daemon and may break.
  - Concurrent *same-protocol* runs are safe (per-request uuid tokens keep callbacks isolated).
  - After switching to a branch that changes the callback protocol, run `tt tunnel stop` so the next run respawns the daemon with the new code.
- **Fallback / poll path.** If cloudflared is missing/fails to start, or mode is `poll`: inject an unreachable placeholder `callback` (`PLACEHOLDER_CALLBACK`, so the request stays valid TRAPI since `callback` is required), then poll `asyncquery_status` every 10s until done/timeout (`CONFIG.timeout`, default 300s), then GET `response_url`.
- **Laziness.** Infrastructure is lazy — all-sync/poll runs start nothing.
- **External deps & limits.**
  - `cloudflared` is an optional external binary (like `fx`).
  - Tunnel callbacks are capped at 100 MB by Cloudflare Free/Pro (remote very-large responses may need `poll`).
  - Docker/LAN local targets may need `callback.host: host.docker.internal` or `callback.bind: 0.0.0.0`.
- **Tunnel readiness & logs.** Before handing the query over, the daemon waits for tunnel readiness (edge connection registered *and* the hostname resolving via public DoH — the details are fiddly and network-dependent; see `callback_daemon.py`) and logs URL/readiness/callbacks/failures to `tunnel-daemon.log` in the state dir — the go-to place when a tunnel "is unavailable."
- **Testing seam:** `TTT_TUNNEL_URL` bypasses cloudflared.

**PK retrieval.** `tt pk` (`retrieve_by_pk.py`) fans out concurrently across all ARS instances to locate the PK, fetches the trace, prompts to pick an ARA child actor, and retrieves that ARA's stored TRAPI response.

- **Merge count.** Metadata printed alongside the payload includes a per-actor **merge count**, tallied by agent from the trace's `merged_versions_list` (a `repr`'d list parsed with `ast.literal_eval`, since a child's own copy is empty).
- **Framing.** Each mode frames its metadata as a `┌ <heading> · <pk>` header + `IndentedBlock` gutter + `└ <status>` close (framed-block rule — see Cross-cutting).
- **Mode flags:**
  - `--trace/-t` — skips the drill-down and outputs the whole trace with its per-actor metadata table.
  - `--raw/-r` — keeps the drill-down but skips `extract_response_payload`, emitting the raw ARS stored response instead of the TRAPI payload. `-t` takes precedence.
  - `--triage/-T` — skips the picker entirely, concurrently fetches **every** ARA child's stored response, and renders each in a `tt test`-style framed block (`run_triage`) with `standard_battery()` results appended.
- **Triage battery reuse is literal.** It builds a synthetic `Query(tests=standard_battery())` + a rebuilt `httpx.Response` and calls `run_query.run_tests`, so the test lines match the runner exactly (which is why `retrieve_by_pk` prints through the **shared** runner `console`).
- **Triage saving.** Triage ignores the view/pipe flags but **honors `-s <path>` to persist every fetched ARA response**: `_save_triage_response` treats `<path>` as a file and, mirroring `tt test`'s multi-save, actor-prefixes it (`<ara>_<name>`) when there's more than one ARA so they don't collide (the extracted TRAPI payload by default, the raw ARS body with `--raw/-r`). One expensive concurrent fetch thus yields durable, addressable artifacts for a later diff/analyze without re-fetching.

**translator_tom (TOM).**

- Query bodies may be raw dicts or TOM model objects (`serialize_body` normalizes them); analyses receive a parsed `translator_tom.Response`.
- TOM is imported lazily, so raw-dict query authoring never loads it.

**Query-body constructors.** `trapi_testing_tools/query_utils.py` provides convenience builders for TOM query bodies.

- `one_hop` — a two-node/one-edge query from category/id/predicate args.
- `from_qg` — wrap an existing `QueryGraph`/`PathfinderQueryGraph` in a `Message`+`Query`.
- `load_json` — load a JSON file as a given TOM model (a bare query graph, a `Message`, or a full `Query`) and reconstruct a complete query body.
- **Common behavior:** all apply a default `submitter` and pass extra keyword args through as body-level fields.
- `tt query` (the `query` command above) is the CLI wrapper over `one_hop` for firing an ad-hoc single-hop query without a file.

## Conventions

- Ruff is configured broadly (pydocstyle google convention, type-annotation rules, pathlib-over-os, etc.) with line length 88. Docstrings are required on public functions/classes.
- New analyses/queries/validators need no wiring — just drop a file in the right directory following the base-class contract.

## Writing this document

AGENTS.md is for an agent **working on TTT's code**, not using the CLI. Keep every addition to one of two registers: **high-level architecture** (how the pieces fit, non-obvious invariants, gotchas that would recur) or **extended interface detail beyond the skill's scope** (internals a contributor needs that `.agents/skills/trapi-testing/SKILL.md` deliberately omits). Do **not** add devlog-esque material — change narration, "now uses X instead of Y", aesthetic/UI trivia self-evident from the code, or a running record of what shipped. If a fact only makes sense as "what changed," it belongs in a commit message or `IDEAS.md`, not here. Usage guidance for an agent driving the CLI goes in SKILL.md, not here.
