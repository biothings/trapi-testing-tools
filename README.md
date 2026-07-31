# TRAPI Testing tools

A set of command-line tools for rapidly testing and analyzing various TRAPI resources.

## Getting started

Install a JSON viewer for inspecting responses. The default is fx: [https://fx.wtf/install](https://fx.wtf/install). You can use different viewers (such as [jless](https://jless.io/)), see [Configuring JSON viewer](#configuring-json-viewer).

This project uses uv for package/dependency management. Install instructions: [https://docs.astral.sh/uv/getting-started/installation/](https://docs.astral.sh/uv/getting-started/installation/)

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

To run a full test of everything in the routine folder, against your local instance, viewing only failed tests:

```bash
tt test -a -d -e bte.local
```

### Specific tests

You can run the command `tt test` with no other arguments to interactively select tests. If you know the test(s) you want to run, you can provide them as arguments:

```bash
tt test trapi-testing-tools/queries/routine/feature/creative/drug_treats_disease.hurl
```

### Retrieving a response from an ARS PK

A tool exists for retrieving responses from a PK:

```bash
tt pk <your-pk-here>
```

For more information, see `tt pk --help`

### Analyzing a response

`tt analyze` runs one or more analyses against a TRAPI response. Select a response from a file with `-f`, or pipe one in:

```bash
# interactively pick analyses to run against a saved response
tt analyze -f response.json

# run specific analyses
tt analyze -f response.json NodeFrequency SupportGraphHierarchy

# pipe in a response and pipe out result
tt test queries/my_query.py -e retriever.ci -p | tt analyze NodeFrequency -p | jq
```

Some analyses take arguments, passed after a `--` separator. You can view analysis options with `-- --help`.

```bash
tt analyze PathCount -f response.json -- --start NCBIGene:3778 --end MONDO:0000437
```

## Writing a query

You can add your own queries to be used in `tt test`, the specification is relatively simple:

```python
# Some tests are provided for validating the response
from tests import http

method = "POST"  # Use any HTTP method here
endpoint = "/v1/query"  # The endpoint to be applied to the tool
headers = {}  # You can optionally specify headers
params = {...}  # You can optionally pass URL parameters as a dictionary of param_name: value
body = {...}  # You can optionally add a body in the form of a dictionary
tests = [http.status(200)]  # You can optionally set tests to validate the response
```

The `body` may be a plain dict (as above) or a [translator_tom](https://github.com/NCATSTranslator/TRAPIObjectModeling) (TOM) model.

Queries placed under the `queries/routine` directory will be run when `tt test` is invoked with the option `--all`

### Multi-query tests

You can instead supply a list named `steps` of `Query` objects. The steps run in order against the same environment:


```python
from tests import http
from trapi_testing_tools.types import Query
from copy import deepcopy

body1 = {...}  # A query body
body2 = {...} # Another body, can modify a copy of previous

steps = [
    Query(method="POST", endpoint="/query", body=body1, tests=[http.status(200)]),
    Query(method="POST", endpoint="/query", body=body2, tests=[http.status(200)]),
]
```

## Writing a test

Queries use tests, kept in `tests/` to make repeatable checks on query responses. Tests can signal a pass/fail, and/or provide arbitrary information as output to the terminal. An example:

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

There's a premade test collection of standard desireable tests called `standard_battery()` in `tests/battery.py`. Use that file for adding other commonly-reused sets.

```python
from tests.battery import standard_battery
# standard_battery() returns a list which you can concat with custom tests.
tests = standard_battery()
```

## Writing an analysis

Analyses written under `analysis/` are discovered automatically. An analysis transforms a parsed TRAPI `Response` into JSON-serializable output, with the docstring being used as a display name.


```python
import typer

from translator_tom import Response

from analysis.base_analysis import Analysis, ParametrizedAnalysis, AnalysisOutput


##### A simple analysis #####
class ResponseShape(Analysis):
    """node frequency across kg edges."""

    @staticmethod
    def analyze(response: Response) -> AnalysisOutput:
        kg = response.message.knowledge_graph
        return {
            "nodes": len(kg.nodes_dict),
            "edges": len(kg.edges_dict),
            "results": len(response.message.results_list
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

Services are specified in [`config.yaml`](https://github.com/biothings/bte-hurl/blob/main/config.yaml). See the bte entry for an example.

Services are selected either interactively or by adding `-e <service>.<level>` to the command. You can change the default service so you can more quickly type just the level when supplying the option to the command.

## Configuring JSON viewer

You can choose to view responses, in which case a separate viewer program is used. By default, `fx` is used, but this can be configured to any program available in your shell. Configure in `config.yaml`:

```yaml
viewer: jless
```

> [!NOTE]
> The viewer is only used for JSON responses. Non-JSON responses fall back to `less`
