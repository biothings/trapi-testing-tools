import importlib
from collections.abc import Sized
from contextlib import redirect_stdout
from pathlib import Path
from sys import stderr
from typing import Literal, overload

import typer
from InquirerPy.prompts.fuzzy import FuzzyPrompt
from rich.console import Console

import analysis as analysis_list
import queries as query_list
from analysis.base_analysis import Analysis, AnalysisClass, ParametrizedAnalysis
from trapi_testing_tools.types import OutputModes
from trapi_testing_tools.utils import ENVIRONMENT_MAPPING, is_interactive

console = Console(stderr=True)


@overload
def set_queries(
    queries: list[Path] | None, multi: Literal[True]
) -> tuple[list[Path], bool]: ...


@overload
def set_queries(
    queries: list[Path] | None, multi: Literal[False]
) -> tuple[Path, bool]: ...


@overload
def set_queries(queries: list[Path] | None) -> tuple[list[Path], bool]: ...


def set_queries(
    queries: list[Path] | None, multi: bool = True
) -> tuple[list[Path], bool] | tuple[Path, bool]:
    """Given the command arguments, ensure queries are selected.

    Directory arguments are expanded recursively into the query files.
    """
    used_interactive = False
    if queries is None:
        valid_files = [
            str(
                path.relative_to(Path(query_list.__path__[0]).resolve()).with_suffix("")
            )
            for path in Path(query_list.__path__[0]).rglob("**/*.py")
        ]
        with redirect_stdout(stderr):
            selection: list[str] = FuzzyPrompt(
                message="Select query file(s)...",
                choices=valid_files,
                multiselect=multi,
                border=True,
                instruction="(Type to filter, Tab to select, Enter to confirm)",
                info=True,
            ).execute()
        if len(selection) == 0:
            raise typer.Abort()

        queries = [
            Path("./queries").joinpath(f"{path_str}.py").resolve()
            for path_str in (selection if type(selection) is list else [selection])
        ]
        used_interactive = True

    # Recursively obtain queries from directory args
    expanded: list[Path] = []
    for path in queries:
        if path.is_dir():
            matches = sorted(
                p.resolve() for p in path.rglob("*.py") if "__pycache__" not in p.parts
            )
            if not matches:
                console.print(
                    f"INFO: no query files found in {path}",
                    style="italic bright_black",
                )
            expanded.extend(matches)
        else:
            expanded.append(path)
    queries = expanded

    if len(queries) == 0:
        raise typer.Abort()

    if (type(queries) is list) and not multi:
        return queries[0], used_interactive
    return queries, used_interactive


def set_environment(
    environment: list[str] | None, multi: bool = True
) -> tuple[list[str], bool]:
    """Ensure one or more target environments have been selected.

    With ``multi`` (the default) the interactive picker is multiselect; multiple
    environments run each query against each, sequentially.
    """
    used_interactive = False
    if not environment:
        with redirect_stdout(stderr):
            selection = FuzzyPrompt(
                message="Select environment(s)..."
                if multi
                else "Select environment...",
                choices=[key for key in ENVIRONMENT_MAPPING if "." in key],
                multiselect=multi,
                instruction="(Type to filter, Tab to select, Enter to confirm)",
                border=True,
            ).execute()
        environment = selection if isinstance(selection, list) else [selection]
        used_interactive = True

    unknown = [env for env in environment if env not in ENVIRONMENT_MAPPING]
    if not environment or unknown:
        console.print(
            f"Environment{'s' if len(unknown) > 1 else ''} "
            f"{', '.join(unknown) or '(none)'} must be one of "
            f"{', '.join(ENVIRONMENT_MAPPING.keys())}"
        )
        raise typer.Exit(1)

    return environment, used_interactive


def set_output_modes(  # noqa: PLR0913
    view: bool | None,
    save: Path | None,
    no_save: bool,
    pipe: bool,
    selection: Sized,
    allow_multi: bool = False,
) -> OutputModes:
    """Set output modes based on given arguments.

    Without an interactive terminal the view/save prompts can't be answered, so
    anything left unspecified defaults to skipping (no-view/no-save). ``allow_multi``
    permits ``--pipe`` across multiple items (the test command aggregates them into
    one report); other commands still reject piping more than one.
    """
    default_mode = "prompt" if is_interactive() else "skip"
    view_mode = default_mode
    save_mode = default_mode
    if view is not None:
        view_mode = "every" if view else "skip"
    if save is not None:
        save_mode = "every"
    if no_save:
        save_mode = "skip"
    if pipe:
        if not allow_multi and len(selection) > 1:
            console.print("Pipe mode only supported for a single query/analysis.")
            raise typer.Exit(1)
        view_mode = "pipe"
        save_mode = "skip"

    return view_mode, save_mode


def discover_analyses() -> dict[str, AnalysisClass]:
    """Import every analysis module and collect the declared analyses by name."""
    found = dict[str, AnalysisClass]()
    base_dir = Path(analysis_list.__path__[0])
    for path in base_dir.rglob("**/*.py"):
        if path.stem in ("__init__", "base_analysis"):
            continue
        module_name = "analysis." + ".".join(
            path.relative_to(base_dir).with_suffix("").parts
        )
        try:
            module = importlib.import_module(module_name)
        except Exception as error:
            console.print(
                f"WARNING: could not import {module_name}: {error!r}",
                style="yellow",
            )
            continue
        for attr in vars(module).values():
            if (
                isinstance(attr, type)
                and issubclass(attr, Analysis | ParametrizedAnalysis)
                and attr not in (Analysis, ParametrizedAnalysis)
                and not getattr(attr, "__abstractmethods__", None)
            ):
                found[attr.__name__] = attr
    return found


def set_analyses(names: list[str] | None) -> tuple[list[AnalysisClass], bool]:
    """Given the command arguments, ensure analyses are selected."""
    available = discover_analyses()
    used_interactive = False

    if names is None:
        label_to_name = dict[str, str]()
        for name, cls in sorted(available.items()):
            doc = (cls.__doc__ or "").strip().removesuffix(".")
            label_to_name[f"{name}  —  {doc}" if doc else name] = name
        with redirect_stdout(stderr):
            selection: list[str] = FuzzyPrompt(
                message="Select analyses...",
                choices=list(label_to_name),
                multiselect=True,
                border=True,
                instruction="(Type to filter, Tab to select, Enter to confirm)",
                info=True,
            ).execute()
        if len(selection) == 0:
            raise typer.Abort()
        names = [label_to_name[label] for label in selection]
        used_interactive = True

    selected = list[AnalysisClass]()
    for name in names:
        cls = available.get(name) or next(
            (c for n, c in available.items() if n.lower() == name.lower()), None
        )
        if cls is None:
            console.print(
                f"Unknown analysis: {name}. "
                f"Available: {', '.join(sorted(available))}",
                style="red",
            )
            raise typer.Exit(1)
        selected.append(cls)
    return selected, used_interactive
