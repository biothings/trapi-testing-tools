# TRAPI Testing tools

A set of command-line tools for rapidly testing and analyzing various TRAPI resources.

## Getting started

Install a JSON viewer for inspecting responses. The default is fx:
[https://fx.wtf/install](https://fx.wtf/install). You can use different viewers (such as
[jless](https://jless.io/)), see [Configuring JSON viewer](#configuring-json-viewer).

**Optional:** install
[`cloudflared`](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/)
(e.g. `brew install cloudflared`) to receive `/asyncquery` callbacks from **remote**
services via a tunnel (see [Async queries](#async-queries-asyncquery-and-callbacks)).

This project uses uv for package/dependency management. Install instructions:
[https://docs.astral.sh/uv/getting-started/installation/](https://docs.astral.sh/uv/getting-started/installation/)

Clone and set up workspace:

```bash
git clone https://github.com/biothings/trapi-testing-tools
cd trapi-testing-tools
uv sync
# Get into the virtual environment
source .venv/bin/activate
# Alternatively, you can prepend `uv run` to all commands in subsequent sections
```

## Usage

All usage is documented in the `--help` option of the program:

```bash
tt --help
```

Individual subcommands also provide help:

```bash
tt test --help
```

### Routine tests

To run a full test of everything in the routine folder, against your local instance,
viewing only failed tests:

```bash
tt test -d -e retriever.local queries/routine
```

### Specific tests

You can run the command `tt test` with no other arguments to interactively select tests.
If you know the test(s) you want to run, you can provide them as arguments:

```bash
tt test queries/routine/feature/creative/drug_treats_disease.py  # Specific file
tt test queries/routine/feature/creative  # Set of files (recursively) under a folder
```

### Repeating the last test

`tt test -R` (`--repeat`) re-runs the last test invocation, including queries and
environments you picked interactively. Any flags or queries you pass alongside `-R`
override the remembered ones:

```bash
tt test -R                 # repeat the last run exactly
tt test -R -e retriever.ci # repeat, change environment
```

Invocations are remembered per-shell.

### Retrieving a response from an ARS PK

A tool exists for retrieving responses from a PK:

```bash
tt pk <your-pk-here>
```

For more information, see `tt pk --help`

### Analyzing a response

`tt analyze` runs one or more analyses against a TRAPI response. Select a response from
a file with `-f`, or pipe one in:

```bash
# interactively pick analyses to run against a saved response
tt analyze -f response.json

# run specific analyses
tt analyze -f response.json NodeFrequency SupportGraphHierarchy

# pipe the response body into an analysis (-p plain pipes just the body)
tt test queries/my_query.py -e retriever.ci -p plain | tt analyze NodeFrequency -p | jq
```

Some analyses take arguments, passed after a `--` separator. You can view analysis
options with `-- --help`.

```bash
tt analyze PathCount -f response.json -- --start NCBIGene:3778 --end MONDO:0000437
```

## Writing a query

You can add your own queries to be used in `tt test`, the specification is relatively
simple:

```python
# Some tests are provided for validating the response
from tests import http

method = "POST"  # Use any HTTP method here
endpoint = "/query"  # The endpoint to be applied to the tool
headers = {}  # You can optionally specify headers
params = {...}  # You can optionally pass URL parameters as a dictionary of param_name: value
body = {...}  # You can optionally add a body in the form of a dictionary
tests = [http.Status.expect(200)]  # You can optionally set tests to validate the response
```

The `body` may be a plain dict (as above) or a
[translator_tom](https://github.com/NCATSTranslator/TRAPIObjectModeling) (TOM) model.

Async queries initiate a callback tunnel, or failing that, poll (either way, a callback
url is injected, if one is not already present). Submitter, if not set, is auto-injected
as `trapi-testing-tools` (configurable).

### Multi-query tests

You can instead supply a list named `steps` of `Query` objects. The steps run in order
against the same environment:

```python
from tests import http
from trapi_testing_tools.types import Query
from copy import deepcopy

body1 = {...}  # A query body
body2 = {...} # Another body, can modify a copy of previous

steps = [
    Query(method="POST", endpoint="/query", body=body1, tests=[http.Status.expect(200)]),
    Query(method="POST", endpoint="/query", body=body2, tests=[http.Status.expect(200)]),
]
```

#### Follow-up steps

If you need follow-up steps to use a previous step's state, you can write a `FollowUp`:

```python
from tests import http
from trapi_testing_tools.console import console
from trapi_testing_tools.query_utils import one_hop
from trapi_testing_tools.types import FollowUp, Query

DRUG = "PUBCHEM.COMPOUND:5291"  # imatinib


class PinBestResult(FollowUp):
    def build(self, previous, history) -> Query:
        message = previous.response.json()["message"]
        best = message["results"][0]  # imagine results come back score-ordered
        disease = best["node_bindings"]["n1"][0]["id"]
        console.print(f"pinning best result: {disease}")  # ambient commentary
        # use self.derive to only override the dynamic parts of the query
        return self.derive(
            body=one_hop(subject_ids=DRUG, object_ids=disease)
        )


steps = [
    # first hop: pin only the drug, ask which diseases it treats
    Query(
        method="POST",
        endpoint="/query",
        body=one_hop(subject_ids=DRUG, object_category="Disease", predicate="treats"),
        tests=[http.Status.expect(200)],
    ),
    # follow-up: re-run double-pinned against the best-scoring disease it returned
    PinBestResult(method="POST", endpoint="/query", tests=[http.Status.expect(200)]),
]
```

## Writing a test

Queries use tests, kept in `tests/` to make repeatable checks on query responses. Tests
can signal a pass/fail, and/or provide arbitrary information as output to the terminal.
An example:

```python
from typing import override

import httpx

from tests import trapi
from tests.base_test import Test, TestResult


class HasResults(Test):
    """message has results."""  # docstring used for display in terminal

    @override
    @staticmethod
    def test(response: httpx.Response) -> TestResult:
        model = trapi.parse_or_fail(response)  # Converts to TOM model
        if isinstance(model, TestResult):
            return model  # not valid TRAPI, fail with the parse error
        results = model.message.results_list
        # TestResult is a tuple of boolean pass/fail, and string info
        return TestResult(len(results) > 0, f"{len(results)} results")
```

There's a premade test collection of standard desireable tests called
`standard_battery()` in `tests/battery.py`. Use that file for adding other
commonly-reused sets.

```python
from tests.battery import standard_battery
# standard_battery() returns a list which you can concat with custom tests.
tests = standard_battery()
```

## Writing an analysis

Analyses written under `analysis/` are discovered automatically. An analysis transforms
a parsed TRAPI `Response` into JSON-serializable output, with the docstring being used
as a display name.

```python
import typer

from translator_tom import Response

from analysis.base_analysis import Analysis, ParametrizedAnalysis, AnalysisOutput


##### A simple analysis #####
class ResponseShape(Analysis):
    """response shape summary."""

    @staticmethod
    def analyze(response: Response) -> AnalysisOutput:
        kg = response.message.knowledge_graph
        return {
            "nodes": len(kg.nodes),
            "edges": len(kg.edges),
            "results": len(response.message.results_list),
        }


##### An analysis that takes arguments #####
# Arguments may be passed in with the main analyze command after a ` -- `
app = typer.Typer(add_completion=False)

@app.command(context_settings={"ignore_unknown_options": True, "allow_extra_args": True})
def run(ctx: typer.Context, some_arg: str | None = None) -> dict:
    response = ctx.obj
    return {...}


class MyAnalysis(ParametrizedAnalysis):
    """my parametrized analysis."""

    app = app
```

## Adding services to test

Services are specified in
[`config.yaml`](https://github.com/biothings/trapi-testing-tools/blob/main/config.yaml). See the
bte entry for an example.

Services are selected either interactively or by adding `-e <service>.<level>` to the
command. You can change the default service so you can more quickly type just the level
when supplying the option to the command.

## Configuring JSON viewer

You can choose to view responses, in which case a separate viewer program is used. By
default, `fx` is used, but this can be configured to any program available in your
shell. Configure in `config.yaml`:

```yaml
viewer: jless
```

> [!NOTE] The viewer is only used for JSON responses. Non-JSON responses fall back to
> `less`

## Async queries (`/asyncquery`) and callbacks

For `/asyncquery` endpoints, TTT receives the service's callback directly rather than
relying on `/asyncquery_status` polling (services increasingly discard the response
after firing the callback). It stands up a throwaway local HTTP receiver for the run and
injects a per-query `callback` URL into the request body — **unless the query already
specifies a `callback`, in which case that one is respected and TTT falls back to
polling.**

How the receiver is reached is controlled by `callback.mode`, overridable per run with
`--callback-mode` (`--cb`):

- **`auto`** (default) — direct `127.0.0.1` callback for local (loopback/private)
  targets; a
  [cloudflared](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/)
  quick tunnel for remote targets. Falls back to polling if cloudflared isn't installed.
- **`direct`** — always advertise the local receiver directly.
- **`tunnel`** — always use a cloudflared quick tunnel.
- **`poll`** — legacy behavior: poll `/asyncquery_status`, then fetch `response_url`.

For tunnel mode, the receiver + tunnel run in a small **shared background daemon**: the
**first** run starts it and all later runs (any shell) **reuse** it, so you create one
tunnel total rather than one per run — which also avoids Cloudflare rate-limiting. It
persists in the background and shuts itself down after an idle period. Manage it with:

```bash
tt tunnel         # show status (and, in a terminal, offer to start/stop it)
tt tunnel start   # start/prewarm the tunnel now
tt tunnel stop    # stop it
```

> [!NOTE]
> **TLS-intercepting networks / VPNs.** Some corporate networks (or VPNs) intercept
> TLS to `api.trycloudflare.com`, which stops cloudflared from *creating* a tunnel — TTT
> then falls back to polling. A tunnel *already established* survives the VPN coming up,
> so the workaround is: `tt tunnel start` with the VPN off, then connect the VPN and run
> `tt test … --cb tunnel` (it reuses the running tunnel).

> [!NOTE]
> The daemon is global and shared across checkouts. Concurrent runs are isolated by
> per-request tokens, but if you're developing TTT itself and switch to a branch that
> changes the callback protocol, run `tt tunnel stop` first so the next run respawns
> the daemon with that branch's code.
>
> If a tunnel reports as unavailable, the daemon logs why (including cloudflared's own
> output) to `tunnel-daemon.log` in the platform state directory.

```yaml
callback:
  mode: auto            # auto | direct | tunnel | poll
  host: 127.0.0.1       # advertised host for direct mode (e.g. host.docker.internal on Docker Desktop)
  bind: 127.0.0.1       # receiver bind address (0.0.0.0 to reach from a container)
  port: 0               # 0 = OS-assigned ephemeral port
  cloudflared_path: cloudflared
```

> [!NOTE]
> `tunnel`/remote `auto` requires the `cloudflared` binary on your `PATH`
> (`brew install cloudflared`). Quick tunnels are debug-grade (no uptime guarantee,
> fresh URL per run) — fine for interactive use — and Cloudflare's Free/Pro plans cap
> the callback body at 100 MB, so very large remote responses may need `mode: poll`.
> A locally-run service in Docker may need `host: host.docker.internal` (Docker
> Desktop) or `bind: 0.0.0.0`.
