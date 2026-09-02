from pathlib import Path
from typing import Annotated, Any

import typer
from click.core import ParameterSource
from rich.console import Console

from trapi_testing_tools.callback import CallbackMode
from trapi_testing_tools.commands.utils import (
    set_environment,
    set_output_modes,
    set_queries,
)
from trapi_testing_tools.last_run import load_last_test, save_last_test
from trapi_testing_tools.report import PipeMode
from trapi_testing_tools.run_query import run_queries
from trapi_testing_tools.utils import (
    ENVIRONMENT_MAPPING,
)

# test() params that make up a repeatable invocation (also the persisted keys).
_REPEATABLE_PARAMS = (
    "queries",
    "environment",
    "debug",
    "view",
    "save",
    "no_save",
    "pipe",
    "against",
)

console = Console(stderr=True)
app = typer.Typer(
    no_args_is_help=True,
    context_settings=dict(help_option_names=["-h", "--help"]),
)


def _coerce_persisted(name: str, value: Any) -> Any:
    """Convert a persisted JSON value back to the runtime type ``test()`` expects."""
    if value is None:
        return None
    if name == "queries":
        return [Path(part) for part in value]
    if name in ("save", "against"):
        return Path(value)
    if name == "pipe":
        return PipeMode(value)
    return value


def _apply_repeat(  # noqa: PLR0913
    ctx: typer.Context,
    *,
    queries: list[Path] | None,
    environment: list[str] | None,
    debug: bool,
    view: bool | None,
    save: Path | None,
    no_save: bool,
    pipe: PipeMode | None,
    against: Path | None,
) -> tuple[
    list[Path] | None,
    list[str] | None,
    bool,
    bool | None,
    Path | None,
    bool,
    PipeMode | None,
    Path | None,
]:
    """Fill un-typed ``test()`` params from the last saved invocation (for ``--repeat``).

    Params the user typed on this command line win (overrides); the rest are taken from
    the persisted invocation when present. Queries/environment are left ``None`` when
    neither typed nor remembered, so the normal interactive prompt still fires.
    """
    current: dict[str, Any] = {
        "queries": queries,
        "environment": environment,
        "debug": debug,
        "view": view,
        "save": save,
        "no_save": no_save,
        "pipe": pipe,
        "against": against,
    }
    typed = {
        name
        for name in _REPEATABLE_PARAMS
        if ctx.get_parameter_source(name) == ParameterSource.COMMANDLINE
    }
    # `queries` is variadic (Click always reports it COMMANDLINE), so use its value as the "given?" signal.
    typed.discard("queries")
    if queries is not None:
        typed.add("queries")

    last = load_last_test()
    if last is None and not typed:
        console.print("No previous test to repeat.", style="red")
        raise typer.Exit(1)
    last = last or {}

    for name in _REPEATABLE_PARAMS:
        if name not in typed and name in last:
            current[name] = _coerce_persisted(name, last[name])

    return (
        current["queries"],
        current["environment"],
        current["debug"],
        current["view"],
        current["save"],
        current["no_save"],
        current["pipe"],
        current["against"],
    )


@app.command("test | t", help="Run a query.")
def test(  # noqa: PLR0913
    ctx: typer.Context,
    queries: Annotated[
        list[Path] | None,
        typer.Argument(help="One or more query files or folders (recursive) to run."),
    ] = None,
    environment: Annotated[
        list[str] | None,
        typer.Option(
            "--environment",
            "--env",
            "-e",
            help="Environment(s) to run against (e.g. retriever.dev). Multiple environments run queries against each.",
        ),
    ] = None,
    debug: Annotated[
        bool,
        typer.Option(
            "--debug",
            "-d",
            help="Only surface failing queries: stop to view/save them, or (when piping) keep only their responses.",
        ),
    ] = False,
    view: Annotated[
        bool | None,
        typer.Option(
            "--view/--no-view",
            "-v/-V",
            help="View response body in jless after each file completes (normal/debug modes).",
            show_default="Prompt",
        ),
    ] = None,
    save: Annotated[
        Path | None,
        typer.Option(
            "--save",
            "-s",
            help="Write response to path. Will prefix with query name for multiple files.",
        ),
    ] = None,
    no_save: Annotated[
        bool,
        typer.Option(
            "--no-save",
            "-S",
            help="Don't save response and skip prompts to do so.",
        ),
    ] = False,
    pipe: Annotated[
        PipeMode | None,
        typer.Option(
            "--pipe",
            "-p",
            help="Pipe JSON to stdout in the given shape: 'plain' (response "
            "body/bodies, for chaining into tt analyze), 'report' (run/test report, "
            "no bodies), or 'full' (report with bodies).",
        ),
    ] = None,
    repeat: Annotated[
        bool,
        typer.Option(
            "--repeat",
            "-R",
            help="Repeat the last test invocation. Any flags/queries given this run "
            "override the remembered ones.",
        ),
    ] = False,
    callback_mode: Annotated[
        CallbackMode | None,
        typer.Option(
            "--callback-mode",
            "--cb",
            help="How async /asyncquery results are received (overrides config): "
            "auto, tunnel, direct, or poll.",
        ),
    ] = None,
    against: Annotated[
        Path | None,
        typer.Option(
            "--against",
            "-a",
            help="Diff the run's final response against this TRAPI response file "
            "(structural). Overrides any --pipe output with the diff.",
        ),
    ] = None,
) -> None:
    """Run one or more queries against one or more environments."""
    used_interactive = False

    if repeat:
        (
            queries,
            environment,
            debug,
            view,
            save,
            no_save,
            pipe,
            against,
        ) = _apply_repeat(
            ctx,
            queries=queries,
            environment=environment,
            debug=debug,
            view=view,
            save=save,
            no_save=no_save,
            pipe=pipe,
            against=against,
        )

    queries, used_interactive = set_queries(queries)
    environment, used_interactive = set_environment(environment)
    output_modes = set_output_modes(
        view, save, no_save, pipe is not None, queries, allow_multi=True
    )

    # Persist the resolved invocation (incl. interactive picks) for `-R`, before running so failures still save.
    save_last_test(
        {
            "queries": [str(query) for query in queries],
            "environment": environment,
            "debug": debug,
            "view": view,
            "save": str(save) if save is not None else None,
            "no_save": no_save,
            "pipe": pipe.value if pipe is not None else None,
            "against": str(against) if against is not None else None,
        }
    )

    # Output hint to repeat quicker
    if used_interactive:
        opts = [f"-e {env}" for env in environment]
        if debug:
            opts.append("-d")
        if view is not None:
            opts.append("-v" if view else "-V")
        if save is not None:
            opts.append(f"-s {save}")
        if no_save:
            opts.append("-S")
        if pipe is not None:
            opts.append(f"-p {pipe.value}")
        if callback_mode is not None:
            opts.append(f"--cb {callback_mode.value}")
        if against is not None:
            opts.append(f"--against {against}")
        console.print(
            f"\\[Hint] Re-run this command more quickly using: tt test {' '.join(opts)} {' '.join(str(q.relative_to(Path.cwd())) for q in queries)}"
            " (or just: tt test -R)",
            style="italic bright_black",
            soft_wrap=True,
            highlight=False,
        )

    targets = [(env, ENVIRONMENT_MAPPING[env]) for env in environment]
    passed = run_queries(
        queries,
        targets,
        output_modes,
        save,
        debug,
        pipe,
        callback_mode=callback_mode,
        against=against,
    )

    if not passed:
        raise typer.Exit(1)
