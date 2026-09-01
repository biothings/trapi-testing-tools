import asyncio
import json
import shutil
import subprocess
import zipfile
from collections.abc import Iterator
from contextlib import contextmanager, redirect_stdout
from dataclasses import replace
from http import HTTPStatus
from pathlib import Path
from sys import stderr, stdin
from types import CoroutineType, ModuleType
from typing import Any, Literal, cast, get_args, override

import httpx
from InquirerPy.prompts.confirm import ConfirmPrompt
from InquirerPy.prompts.filepath import FilePathPrompt
from InquirerPy.prompts.fuzzy import FuzzyPrompt
from natsort import natsorted
from platformdirs import PlatformDirs
from rich import progress
from rich.console import (
    Console,
    ConsoleOptions,
    ConsoleRenderable,
    Group,
    RenderHook,
    RenderResult,
)
from rich.highlighter import NullHighlighter
from rich.live import Live
from rich.panel import Panel
from rich.segment import Segment
from rich.styled import Styled
from rich.text import Text
from translator_tom import TOMBase

from tests.base_test import Test
from trapi_testing_tools.config import CONFIG
from trapi_testing_tools.console import console
from trapi_testing_tools.types import HTTPMethod, Query, TestType

SYNC_BASIC_CLIENT = httpx.Client(follow_redirects=True, timeout=None)
ASYNC_BASIC_CLIENT = httpx.AsyncClient(follow_redirects=True, timeout=None)


ENVIRONMENT_MAPPING = dict[str, str]()
default = None
for env, levels in CONFIG.environments.items():
    for level, url in levels.items():
        ENVIRONMENT_MAPPING[f"{env}.{level}"] = url

for level, url in CONFIG.environments[CONFIG.default_environment].items():
    ENVIRONMENT_MAPPING[level] = url


def is_interactive() -> bool:
    """Whether an interactive terminal is attached for prompting."""
    return stdin.isatty() and stderr.isatty()


def format_size(num_bytes: int) -> str:
    """Human-readable byte count (e.g. ``12.3 MB``), using 1024-based units."""
    step = 1024
    size = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < step or unit == "TB":
            precision = 0 if unit == "B" else 1
            return f"{size:.{precision}f} {unit}"
        size /= step
    return f"{size:.1f} TB"


def maybe_print_traceback(
    message: str = "Print traceback for this error?",
) -> None:
    """Offer to print the current exception's traceback.

    Skips prompt/output if no TTY is available.
    """
    if not is_interactive():
        return
    with redirect_stdout(stderr):
        if ConfirmPrompt(message, default=False).execute():
            console.print_exception(show_locals=True)


class _Gutter:
    """Render a child with a ``│ `` gutter on every line, wrapped ones included."""

    def __init__(self, renderable: ConsoleRenderable) -> None:
        self.renderable = renderable

    def __rich_console__(
        self, console: Console, options: ConsoleOptions
    ) -> RenderResult:
        prefix = Segment("│ ", console.get_style("rule.line"))
        inner = options.update_width(max(1, options.max_width - 2))
        for line in console.render_lines(self.renderable, inner, pad=False):
            yield prefix
            yield from line
            yield Segment.line()


class IndentedBlock(RenderHook):
    """Render text as an indented block with a ``│ `` gutter on every wrapped line."""

    @override
    def process_renderables(
        self, renderables: list[ConsoleRenderable]
    ) -> list[ConsoleRenderable]:
        return [_Gutter(r) if isinstance(r, Text | Panel) else r for r in renderables]


class _CommentStyle(RenderHook):
    """Recolor printed renderables to comment-color (matches the re-run hint)."""

    @override
    def process_renderables(
        self, renderables: list[ConsoleRenderable]
    ) -> list[ConsoleRenderable]:
        return [Styled(r, "italic bright_black") for r in renderables]


@contextmanager
def comment_console() -> Iterator[None]:
    """Within the block, everything printed to the runner `console` is comment-colored.

    Frames a `FollowUp.build`'s own logging as ambient commentary (highlighting off for a
    uniform grey, like the re-run hint).
    """
    highlighter = console.highlighter
    console.highlighter = NullHighlighter()
    console.push_render_hook(_CommentStyle())
    try:
        yield
    finally:
        console.pop_render_hook()
        console.highlighter = highlighter


def should_output(
    output: object,
    output_type: Literal["view", "save"],
    mode: Literal["prompt", "skip", "every"],
    subject: str = "response",
) -> bool:
    """Based on user view/output flags, determine if the current item should be output."""
    if output is None or mode == "skip":
        return False
    output = True
    if mode == "every":
        return True
    with redirect_stdout(stderr):  # Otherwise set to "prompt"
        return ConfirmPrompt(
            message=f"{output_type.capitalize()} {subject} body?", default=True
        ).execute()


def handle_output(
    output: object | None,
    view_mode: Literal["prompt", "skip", "every", "pipe"],
    save_mode: Literal["prompt", "skip", "every"],
    save_path: Path | None,
    subject: str = "response",
) -> None:
    """Based on the given view/output modes, handle user appropriate interactions."""
    if output is None:
        return
    if view_mode == "pipe":
        print(json.dumps(output) if isinstance(output, dict | list) else output)
        return

    if should_output(output, "view", view_mode, subject):
        if isinstance(output, dict | list):
            subprocess.run(
                CONFIG.viewer,
                input=json.dumps(output),
                shell=True,
                text=True,
                check=False,
            )
        else:
            subprocess.run(
                "less", input=str(output), shell=True, text=True, check=False
            )

    if should_output(
        output,  # pyright: ignore[reportUnknownArgumentType]
        "save",
        save_mode,
        subject,
    ):
        if not save_path:
            with redirect_stdout(stderr):
                save_path = Path(
                    FilePathPrompt(
                        message="Enter a path to save to:",
                        only_directories=True,
                    ).execute()
                )
        save_path.parent.mkdir(parents=True, exist_ok=True)
        with save_path.open("w", encoding="utf8") as file:
            if isinstance(output, dict | list):
                json.dump(output, file)
            else:
                file.write(str(output))


def serialize_body(body: object) -> dict[str, Any] | list[Any] | None:
    """Normalize a query body to a JSON-serializable dict/list (or None).

    Mostly for handling TOM objects.
    """
    if body is None or isinstance(body, dict | list):
        return cast("dict[str, Any] | list[Any] | None", body)

    if isinstance(body, TOMBase):
        return body.to_dict()

    raise AttributeError("Query body must be a dict, list, TOM model, or None.")


_TRAPI_QUERY_ENDPOINTS = ("/query", "/asyncquery")


def _is_trapi_query(query: Query) -> bool:
    """Whether a query looks like a TRAPI query submission.

    Gated on both signals: the endpoint is a TRAPI query path, and the (serialized)
    body structurally matches a TRAPI query envelope — a `message` with a `query_graph`.
    """
    endpoint = (query.endpoint or "").rstrip("/")
    if not endpoint.endswith(_TRAPI_QUERY_ENDPOINTS):
        return False
    body = query.body
    message = body.get("message") if isinstance(body, dict) else None
    return isinstance(message, dict) and "query_graph" in message


def inject_default_submitter(query: Query) -> Query:
    """Backfill the configured `submitter` into a TRAPI query body when absent.

    No-op when auto-injection is disabled (`CONFIG.submitter` empty), the query isn't a
    TRAPI query, or the body already sets `submitter` (author-set values are respected).
    Assumes the body is already serialized (a dict), as after `serialize_body`.
    """
    if not CONFIG.submitter or not _is_trapi_query(query):
        return query
    body = cast("dict[str, Any]", query.body)
    if "submitter" in body:
        return query
    return replace(query, body={"submitter": CONFIG.submitter, **body})


def _query_version(query_module: ModuleType) -> str:
    """The TRAPI version a file targets: its `trapi_version` global (default ``"1.6"``)."""
    version = getattr(query_module, "trapi_version", "1.6")
    if version not in ("1.6", "2.0"):
        raise AttributeError(
            f"Query trapi_version must be '1.6' or '2.0', got {version!r}."
        )
    return version


def parse_query(query_module: ModuleType) -> list[Query]:
    """Check that query has required options."""
    queries: list[Query]
    version = _query_version(query_module)

    if hasattr(query_module, "steps"):
        # Normalize TOM objects; the module-level trapi_version governs every step.
        queries = [
            replace(step, body=serialize_body(step.body), trapi_version=version)
            for step in query_module.steps
        ]
    else:
        method = getattr(query_module, "method", "GET")
        if not isinstance(method, str) or method not in get_args(HTTPMethod):
            raise AttributeError("Query method must be a valid HTTP Method.")

        endpoint = getattr(query_module, "endpoint", None)
        if endpoint is None:
            raise AttributeError("Query must define an endpoint.")

        params = getattr(query_module, "params", {})
        if not isinstance(params, dict):
            raise AttributeError("Query params must be a dict.")
        headers = getattr(query_module, "headers", {})
        if not isinstance(headers, dict) or any(
            not isinstance(key, str) or not isinstance(value, str)
            for key, value in headers.items()  # pyright:ignore[reportUnknownVariableType]
        ):
            raise AttributeError(
                "Query headers must a dict of header-value string pairs."
            )

        # Normalize in case of TOM object
        body = serialize_body(getattr(query_module, "body", None))

        tests = getattr(query_module, "tests", None)
        if not isinstance(tests, list | None) or (
            isinstance(tests, list)
            and any(not issubclass(test, Test) for test in tests)  # pyright:ignore[reportUnknownVariableType]
        ):
            raise AttributeError("Query tests must be defined using Test class.")

        queries = [
            Query(
                method=cast(HTTPMethod, method),
                endpoint=endpoint,
                params=cast(dict[str, Any], params),
                headers=cast(dict[str, str], headers),
                body=body,
                tests=cast(list[type[Test]], tests),
                trapi_version=cast(Literal["1.6", "2.0"], version),
            )
        ]

    return [inject_default_submitter(query) for query in queries]


def cache_tests() -> None:
    """Cache repo tests locally."""
    try:
        test_repo = CONFIG.test_repo

        # Prep a cache directory
        dirs = PlatformDirs("trapi-testing-tools", "biothings")
        cache_dir = dirs.user_cache_path / f"tests/{test_repo.replace('/', '~')}"
        cache_dir.mkdir(parents=True, exist_ok=True)
        archive_path = cache_dir / "archive"
        unzip_dir = cache_dir / "repo"
        local_update_file = cache_dir / "updated_date"

        repo_url = f"https://api.github.com/repos/{test_repo}"

        with console.status("Checking for cache updates...") as status:
            needs_update = True
            response = SYNC_BASIC_CLIENT.get(repo_url)
            response.raise_for_status()
            body = response.json()
            remote_update = body["updated_at"]
            local_update = ""
            if local_update_file.exists():
                with local_update_file.open(encoding="utf8") as file:
                    local_update = file.read()
                needs_update = local_update != remote_update

            if not needs_update:
                console.print(
                    f"{test_repo}: Cache is up-to-date and contains {len([path for path in unzip_dir.rglob('*') if path.is_file()])} files.",
                    style="italic bright_black",
                )
                return
            else:
                console.print(
                    f"{test_repo}: Cache needs update: new update {remote_update} | current update {local_update or 'None'}",
                    style="italic bright_black",
                    highlight=False,
                )

            status.update("Getting repository contents...")
            with (
                archive_path.open("wb") as archive_file,
                SYNC_BASIC_CLIENT.stream(
                    "GET",
                    f"{repo_url}/zipball",
                ) as response,
            ):
                for chunk in response.iter_bytes():
                    archive_file.write(chunk)
                    status.update(
                        f"Getting repository contents...({response.num_bytes_downloaded / 1000}kb)"
                    )

            # Clean up old unzip, then new archive
            status.update("Extracting repository contents...")
            shutil.rmtree(unzip_dir, ignore_errors=True)
            with zipfile.ZipFile(archive_path) as zipped_file:
                zipped_file.extractall(unzip_dir)
            archive_path.unlink()

            # Move repo up one
            status.update("Organizing...")
            extraneous_dir = next(unzip_dir.glob("*"))
            for item in extraneous_dir.glob("*"):
                item.rename(unzip_dir / f"{item.stem}{item.suffix}")
            shutil.rmtree(extraneous_dir, ignore_errors=True)

            # Now that everything has succeeded, we can set the update date
            status.update("Writing update date...")
            if not local_update_file.exists():
                with local_update_file.open("w", encoding="utf8") as file:
                    file.write(remote_update)

        console.print(
            f"Cached {len([path for path in unzip_dir.rglob('*') if path.is_file()])} files from {test_repo}.",
            style="italic bright_black",
        )
    except Exception as error:
        console.print(
            f"[red]ERROR:[/]: An error occurred while checking/updating cache: {error!r}"
        )
        with redirect_stdout(stderr):
            if ConfirmPrompt(
                "Print traceback for this error?", default=False
            ).execute():
                console.print_exception(show_locals=True)


def select_tests(test_type: Literal["asset", "case", "suite"]) -> list[Path]:
    """Prompt user to fuzzy-select tests using test ID/name/desc."""
    test_repo = CONFIG.test_repo
    dirs = PlatformDirs("trapi-testing-tools", "biothings")
    cache_dir = dirs.user_cache_path / f"tests/{test_repo.replace('/', '~')}"

    test_dir = cache_dir / f"repo/test_{test_type}s"
    test_files = test_dir.glob("*.json")
    file_prompts = list[str]()
    prompt_to_fpath = dict[str, Path]()
    for test_path in test_files:
        with test_path.open() as file:
            test = json.load(file)
            desc = test["description"] if test_type == "suite" else test["name"]
            if desc is None:
                desc = "<No Name>"
            prompt = f"{test['id']}: {desc}"
            file_prompts.append(prompt)
            prompt_to_fpath[prompt] = test_path

    selection = FuzzyPrompt(
        message=f"Select test {test_type}(s)...",
        choices=natsorted(file_prompts),
        multiselect=True,
        border=True,
        instruction="(Type to filter, Tab to select, Enter to confirm)",
        info=True,
    ).execute()

    return [prompt_to_fpath[prompt] for prompt in selection]


async def check_api(
    instance_name: str,
    instance_url: str,
    max_name_len: int,
    progress: progress.Progress,
) -> bool:
    """Check that the given API is responsive, updating the given status."""
    task = progress.add_task(f" {instance_name:>{max_name_len}} querying...", total=1)
    try:
        response = await ASYNC_BASIC_CLIENT.get(f"{instance_url}/query", timeout=10)
        if response.status_code != HTTPStatus.METHOD_NOT_ALLOWED:
            response.raise_for_status()
        time = round(response.elapsed.total_seconds() * 1000)
        progress.update(
            task,
            description=f"[green]✓[/] {instance_name:>{max_name_len}} {time:>5}ms",
            completed=1,
        )
        progress.stop()
        return True
    except httpx.HTTPStatusError as error:
        progress.update(
            task,
            description=f"[red]x {instance_name:>{max_name_len}}[/] HTTP {error.response.status_code}",
            completed=1,
        )
        progress.stop()
        return False
    except httpx.RequestError as error:
        progress.update(
            task,
            description=f"[red]x  {instance_name:>{max_name_len}}[/] {error!r}",
            completed=1,
        )
        progress.stop()
        return False


def check_apps_responsive(apps: list[tuple[str, dict[str, str]]]) -> None:
    """Check that a given list of apps are responsive."""
    for app_name, instances in apps:
        if app_name == "default":
            continue
        console.print(f"[rule.line]{app_name}:[/]")

        max_name_len = max(*[len(key) for key in instances if key != "local"])
        statuses = list[progress.Progress]()
        async_tasks = list[CoroutineType[None, None, bool]]()

        for instance_name, instance_url in instances.items():
            if instance_name == "local":
                continue
            status = progress.Progress(
                progress.TextColumn("[rule.line]│[/]"),
                progress.SpinnerColumn(finished_text=""),
                progress.TextColumn("{task.description}"),
                console=console,
            )
            statuses.append(status)
            async_tasks.append(
                check_api(instance_name, instance_url, max_name_len, status)
            )

        overall = progress.Progress(
            progress.TextColumn("[rule.line]└[/]"),
            progress.SpinnerColumn(finished_text=""),
            progress.TextColumn("{task.description}"),
            console=console,
            transient=True,
        )

        group = Group(*statuses, overall)
        live = Live(group)
        with live:
            task = overall.add_task("Checking instances...", total=1)
            loop = asyncio.get_event_loop()
            result = loop.run_until_complete(asyncio.gather(*async_tasks))
            overall.update(task, completed=1, visible=False)

            passed = len([res for res in result if res])
            report = f"[rule.line]└[/] {passed}/{len(result)} Responding"
            if passed == len(result):
                report = "[rule.line]└[/] [green]✓ All Green![/]"
        console.print(report, highlight=False)
