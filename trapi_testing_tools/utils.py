import asyncio
import json
import shutil
import subprocess
import zipfile
from contextlib import redirect_stdout
from pathlib import Path
from sys import stderr
from typing import Literal, Optional

import httpx
import yaml
from InquirerPy import inquirer
from natsort import natsorted
from platformdirs import PlatformDirs
from rich import progress
from rich.console import Console, Group, RenderHook
from rich.live import Live
from rich.text import Text

SYNC_BASIC_CLIENT = httpx.Client(follow_redirects=True, timeout=None)
ASYNC_BASIC_CLIENT = httpx.AsyncClient(follow_redirects=True, timeout=None)
console = Console(stderr=True)

with open(
    Path(__file__).parent.joinpath("../config.yaml").resolve(), "r"
) as config_file:
    config = yaml.safe_load(config_file)

EnvironmentMapping = {}
default = None
for env, levels in config["environments"].items():
    if env == "default":
        default = levels
        continue
    for level, url in levels.items():
        EnvironmentMapping[f"{env}.{level}"] = url

if default:
    for level, url in config["environments"][default].items():
        EnvironmentMapping[level] = url


class IndentedBlock(RenderHook):
    def process_renderables(self, renderables):
        new_renderables = []
        for renderable in renderables:
            if isinstance(renderable, Text):
                new_renderables.append(Text("│ ", style="rule.line", end=""))
            new_renderables.append(renderable)
        return new_renderables


def should_output(
    output: object,
    output_type: Literal["view", "save"],
    mode: Literal["prompt", "skip", "every"],
) -> bool:
    if output is None or mode == "skip":
        return False
    output = True
    if mode == "every":
        return True
    with redirect_stdout(stderr):  # Otherwise set to "prompt"
        return inquirer.confirm(
            message=f"{output_type.capitalize()} response body?", default=True
        ).execute()


def handle_output(
    output: object,
    view_mode: Literal["prompt", "skip", "every", "pipe"],
    save_mode: Literal["prompt", "skip", "every"],
    save_path: Optional[Path],
):
    if output is None:
        return
    if view_mode == "pipe":
        print(json.dumps(output) if isinstance(output, (dict, list)) else output)
        return

    if should_output(output, "view", view_mode):
        if isinstance(output, dict):
            subprocess.run("fx", input=json.dumps(output), shell=True, text=True)
        else:
            subprocess.run("less", input=str(output), shell=True, text=True)

    if should_output(
        output,
        "save",
        save_mode,
    ):
        if not save_path:
            with redirect_stdout(stderr):
                save_path = Path(
                    inquirer.filepath(
                        message="Enter a path to save to:",
                        only_directories=True,
                    ).execute()
                )
        with open(save_path, "w", encoding="utf8") as file:
            if isinstance(output, dict):
                json.dump(output, file)
            else:
                file.write(str(output))


def cache_tests():
    try:
        test_repo = config["test_repo"]

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
                with open(local_update_file, "r", encoding="utf8") as file:
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
            with open(archive_path, "wb") as archive_file, SYNC_BASIC_CLIENT.stream(
                "GET",
                f"{repo_url}/zipball",
            ) as response:
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
                with open(local_update_file, "w", encoding="utf8") as file:
                    file.write(remote_update)

        console.print(
            f"Cached {len([path for path in unzip_dir.rglob('*') if path.is_file()])} files from {test_repo}.",
            style="italic bright_black",
        )
    except Exception as error:
        console.print(
            f"[red]ERROR:[/]: An error occurred while checking/updating cache: {repr(error)}"
        )
        with redirect_stdout(stderr):
            if inquirer.confirm(
                "Print traceback for this error?", default=False
            ).execute():
                console.print_exception(show_locals=True)


def select_tests(test_type: Literal["asset", "case", "suite"]) -> list[Path]:
    """Prompt user to fuzzy-select tests using test ID/name/desc."""
    test_repo = config["test_repo"]
    dirs = PlatformDirs("trapi-testing-tools", "biothings")
    cache_dir = dirs.user_cache_path / f"tests/{test_repo.replace('/', '~')}"

    test_dir = cache_dir / f"repo/test_{test_type}s"
    test_files = test_dir.glob("*.json")
    file_prompts = []
    prompt_to_fpath = {}
    for test_path in test_files:
        with open(test_path, "r") as file:
            test = json.load(file)
            desc = test["description"] if test_type == "suite" else test["name"]
            if desc is None:
                desc = "<No Name>"
            prompt = f"{test['id']}: {desc}"
            file_prompts.append(prompt)
            prompt_to_fpath[prompt] = test_path

    selection = inquirer.fuzzy(
        message=f"Select test {test_type}(s)...",
        choices=natsorted(file_prompts),
        multiselect=True,
        border=True,
        instruction="(Type to filter, Tab to select, Enter to confirm)",
        info=True,
    ).execute()

    return [prompt_to_fpath[prompt] for prompt in selection]


async def check_api(instance_name, instance_url, max_name_len, progress):
    task = progress.add_task(f" {instance_name:>{max_name_len}} querying...", total=1)
    try:
        response = await ASYNC_BASIC_CLIENT.get(f"{instance_url}/query", timeout=10)
        if not response.status_code == 405:
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
            description=f"[red]x  {instance_name:>{max_name_len}}[/] {repr(error)}",
            completed=1,
        )
        progress.stop()


def check_apps_responsive(apps):
    for app_name, instances in apps:
        if app_name == "default":
            continue
        console.print(f"[rule.line]{app_name}:[/]")

        max_name_len = max(*[len(key) for key in instances.keys() if key != "local"])
        statuses = []
        async_tasks = []

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
