# TRAPI Testing tools

A set of command-line tools for rapidly testing and analyzing various TRAPI resources.

## Getting started

Install fx: [https://fx.wtf/install](https://fx.wtf/install)

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

## Writing a query

You can add your own queries to be used in `tt test`, the specification is relatively simple:

```python
# Some tests are provided for validating the response
from trapi_testing_tools.tests import http

method = "POST"  # Use any HTTP method here
endpoint = "/v1/query"  # The endpoint to be applied to the tool
headers = {}  # You can optionally specify headers
params = {...}  # You can optionally pass URL parameters as a dictionary of param_name: value
body = {...}  # You can optionally add a body in the form of a dictionary
tests = [http.status(200)]  # You can optionally set tests to validate the response
```

Queries placed under the `trapi_testing_tools/queries/routine` directory will be run when `tt test` is invoked with the option `--all`

### Multi-query tests

you can instead supply a list named `steps` with the above values as dictionary entries if you need to test consecutive related queries. See [`trapi_testing_tools/queries/routine/feature/caching/cache.py`](https://github.com/biothings/bte-hurl/blob/main/trapi_testing_tools/queries/routine/feature/caching/cache.py) for a good example.

### Adding services to test

Services are specified in [`config.yaml`](https://github.com/biothings/bte-hurl/blob/main/config.yaml). See the bte entry for an example.

Services are selected either interactively or by adding `-e <service>.<level>` to the command. You can change the default service so you can more quickly type just the level when supplying the option to the command.
