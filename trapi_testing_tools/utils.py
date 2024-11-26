from contextlib import redirect_stdout
import asyncio
import json
import subprocess
from sys import stderr
from typing import Literal, Optional
import httpx
from rich.text import Text
import yaml
from pathlib import Path
import enum
from rich.console import Console, RenderHook
from InquirerPy import inquirer
from rich.pretty import Pretty
from rich import progress
from rich.console import Console, Group, RenderHook
from rich.live import Live
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
async def check_api(instance_name, instance_url, max_name_len, progress):
    task = progress.add_task(f" {instance_name:>{max_name_len}} querying...", total=1)
    try:
        response = await ASYNC_BASIC_CLIENT.get(
            f"{instance_url}/asyncquery_status/HopefullyNonExistentHash", timeout=10
        )
        if not response.status_code == 404:
            response.raise_for_status()
        time = round(response.elapsed.total_seconds() * 1000)
        progress.update(
            task,
            description=f"[green]✓[/] {instance_name:>{max_name_len}} {time:>5}ms",
            completed=1,
        )
        return True
    except httpx.HTTPError as error:
        progress.update(
            task,
            description=f"[red]x  {instance_name:>{max_name_len}}:[/] {repr(error)}",
            completed=1,
        )
        return False


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
            report = f"[rule.line]└[/] {passed}/{len(result)} Responding."
            if passed == len(result):
                report = "[rule.line]└[/] [green]✓ All Green![/]"
        console.print(report, highlight=False)
