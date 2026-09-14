"""Live-progress HTTP fetch shared by every command that issues a request step.

Streams the response body so the interface can transition ``Querying...`` (awaiting the
response headers) → ``Receiving...`` (body streaming in) with a compact braille progress
bar, so a slow, large fetch reads as visible progress rather than a stall. Falls back to
a plain request when the console isn't a terminal, so it never leaks progress into piped
output.
"""

import time
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import timedelta
from typing import Any

import httpx
from rich.console import Group
from rich.live import Live
from rich.text import Text

from trapi_testing_tools.console import console
from trapi_testing_tools.utils import format_size

_BAR_CELLS = 3
# Per-cell fill order: left column top→bottom, then right column — so a cell builds up
# vertically before advancing horizontally, giving 8 sub-levels per cell (0 to 8 dots).
_CELL_LEVELS = "⠀⠁⠃⠇⡇⡏⡟⡿⣿"
_FPS = 12
_INDICATOR = "green"  # bar accent; label text stays the terminal default

# Indeterminate spin: one animation spanning all `_BAR_CELLS` cells (a 3-dot comet orbiting
# the full strip perimeter — top edge, down the right side, bottom edge, up the left side),
# cycled at `_FPS`. Each frame is a full-width braille picture — edit freely; see
# `scratchpad/braille-palette.txt` for every cell and its dot bits.
_SPIN_FRAMES = (
    "⠉⠁⠀",
    "⠈⠉⠀",
    "⠀⠉⠁",
    "⠀⠈⠉",
    "⠀⠀⠙",
    "⠀⠀⠸",
    "⠀⠀⢰",
    "⠀⠀⣠",
    "⠀⢀⣀",
    "⠀⣀⡀",
    "⢀⣀⠀",
    "⣀⡀⠀",
    "⣄⠀⠀",
    "⡆⠀⠀",
    "⠇⠀⠀",
    "⠋⠀⠀",
)


def _bar(fraction: float) -> str:
    """A `_BAR_CELLS`-cell braille bar filled left-to-right to ``fraction`` (0 to 1)."""
    dots = round(max(0.0, min(fraction, 1.0)) * _BAR_CELLS * 8)
    return "".join(
        _CELL_LEVELS[max(0, min(dots - i * 8, 8))] for i in range(_BAR_CELLS)
    )


def _spin(frame: int) -> str:
    """The indeterminate widget: one spin across all cells (pre-receive / unknown length)."""
    return _SPIN_FRAMES[frame % len(_SPIN_FRAMES)]


class FetchProgress:
    """A time-driven fetch indicator (one row: label + spin/bar + byte counts + elapsed).

    Live re-renders it each tick, so the spinner and elapsed clock keep moving even while
    the fetching thread is blocked awaiting headers or between chunks. Reused as a single
    line by `fetch`, or one row per concurrent download in a multi-bar (see `live_rows`).
    """

    def __init__(self, label: str = "Querying...") -> None:
        """Start the elapsed clock; `label` is the row's static caption."""
        self.label = label
        self.downloaded = 0
        self.total = 0
        self._start = time.monotonic()

    def __rich__(self) -> Text:
        """Render the current frame: widget + label + byte counts + elapsed."""
        elapsed_s = time.monotonic() - self._start
        if self.total > 0:
            widget = _bar(self.downloaded / self.total)
            counts = f" {format_size(self.downloaded)} / {format_size(self.total)}"
        else:
            widget = _spin(int(elapsed_s * _FPS))
            counts = f" {format_size(self.downloaded)}" if self.downloaded else ""

        return Text.assemble(
            (widget, _INDICATOR), " ", self.label, counts, f" {elapsed_s:.1f}s"
        )


def _materialize(
    response: httpx.Response, chunks: bytes, start: float
) -> httpx.Response:
    """Rebuild a fully-read `httpx.Response` from streamed chunks, stamping `.elapsed`."""
    result = httpx.Response(
        status_code=response.status_code,
        headers=response.headers,
        content=chunks,
        request=response.request,
    )
    result.elapsed = timedelta(seconds=time.monotonic() - start)
    return result


@contextmanager
def live_rows(rows: list[FetchProgress]) -> Iterator[None]:
    """Show a stack of `FetchProgress` rows under one `Live` for concurrent downloads.

    A no-op when the console isn't a terminal, so piped/non-TTY runs stay quiet.
    """
    if not console.is_terminal:
        yield
        return
    with Live(Group(*rows), console=console, refresh_per_second=_FPS, transient=True):
        yield


def fetch(
    client: httpx.Client,
    method: str,
    url: str,
    **kwargs: Any,
) -> httpx.Response:
    """Issue a request with live Querying→Receiving progress; return a materialized response.

    The returned response is fully read (``.content``/``.json()``/``.raise_for_status()``
    all work) with ``.elapsed`` set. Extra keyword args (``json``/``params``/``headers``/…)
    pass through to httpx.
    """
    if not console.is_terminal:
        return client.request(method, url, **kwargs)

    start = time.monotonic()
    progress = FetchProgress()
    with (
        Live(progress, console=console, refresh_per_second=_FPS, transient=True),
        client.stream(method, url, **kwargs) as response,
    ):
        progress.label = "Receiving..."
        progress.total = int(response.headers.get("Content-Length") or 0)
        chunks = bytearray()
        for chunk in response.iter_raw():  # raw (undecoded) bytes; headers stay valid
            chunks.extend(chunk)
            progress.downloaded = len(chunks)

    return _materialize(response, bytes(chunks), start)


async def stream_into(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    progress: FetchProgress,
    **kwargs: Any,
) -> httpx.Response:
    """Async-stream a request into `progress` (updating its bar); return a materialized response.

    The indicator's spin→bar transition conveys the querying→receiving phases, so `progress`'s
    `label` is left untouched (a static per-download label, e.g. the actor name in a multi-bar).
    """
    start = time.monotonic()
    async with client.stream(method, url, **kwargs) as response:
        progress.total = int(response.headers.get("Content-Length") or 0)
        chunks = bytearray()
        async for (
            chunk
        ) in response.aiter_raw():  # raw (undecoded) bytes; headers stay valid
            chunks.extend(chunk)
            progress.downloaded = len(chunks)

    return _materialize(response, bytes(chunks), start)
