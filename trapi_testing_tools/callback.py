"""Receive `/asyncquery` callbacks via a local HTTP server.

TRAPI `/asyncquery` POSTs the final response to a `callback` URL; services
increasingly discard it afterwards, so polling `/asyncquery_status` returns nothing.
This module stands up a local receiver so TTT gets the response directly.

Reachability depends on the target:
- **direct** (local target): a per-run receiver bound to loopback.
- **tunnel** (remote target): a cloudflared quick tunnel fronting a receiver that
  lives in a detached, *global* daemon (`callback_daemon.py`) shared by all runs on the
  machine, so a single tunnel is reused; it persists in the background and reaps itself
  after an idle period (or on `tt tunnel stop`).
- **poll**: legacy `/asyncquery_status` polling (with a placeholder callback).

The receiver serves `POST /callback/{token}` (services post results here) and
`GET /result/{token}` (a client claims a received body — used to hand callbacks from
the daemon back to a separate `tt test` process).
"""

import ipaddress
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from collections import deque
from collections.abc import Iterator
from contextlib import contextmanager
from enum import StrEnum
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import BufferedIOBase
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlparse
from uuid import uuid4

import httpx
from platformdirs import PlatformDirs

from trapi_testing_tools.config import CONFIG
from trapi_testing_tools.utils import console

ResolvedMode = Literal["tunnel", "direct", "poll"]

# The poll path must still send a callback: an unroutable RFC 2606 `.invalid` placeholder.
PLACEHOLDER_CALLBACK = "http://trapi-testing-tools.invalid/callback"

# How long a client waits for a freshly-spawned daemon to publish a reachable tunnel.
_DAEMON_STARTUP_TIMEOUT = 75


class CallbackMode(StrEnum):
    """Choices for the `--callback-mode` CLI option (mirrors `CallbackConfig.mode`)."""

    auto = "auto"
    tunnel = "tunnel"
    direct = "direct"
    poll = "poll"


def _is_local_target(url: str) -> bool:
    """Whether a target URL points at a loopback/private/local host."""
    host = urlparse(url).hostname or ""
    if host == "localhost" or host.endswith((".localhost", ".local")):
        return True

    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False

    return ip.is_loopback or ip.is_private or ip.is_link_local


def url_reachable(url: str | None, timeout: float) -> bool:
    """Poll ``url`` until an HTTP request succeeds (DNS + edge have propagated).

    Any HTTP response (even 404/5xx) counts; only transport errors are retried.
    """
    if url is None:
        return False

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            httpx.get(url, timeout=5)
            return True
        except httpx.HTTPError:
            time.sleep(1)
    return False


def make_synthetic_response(raw: bytes) -> httpx.Response:
    """Wrap a received callback body as an httpx.Response for the test pipeline."""
    return httpx.Response(
        200, content=raw, headers={"content-type": "application/json"}
    )


def _split_route(path: str) -> tuple[str, str]:
    """Split `/callback/{token}` or `/result/{token}` into ``(route, token)``."""
    match urlparse(path).path.strip("/").split("/"):
        case [route, token]:
            return route, token
        case _:
            return "", ""


def _read_chunked(stream: BufferedIOBase) -> bytes:
    """Decode a `Transfer-Encoding: chunked` request body."""
    chunks: list[bytes] = []
    while True:
        size_line = stream.readline().split(b";", 1)[0].strip()
        size = int(size_line, 16)
        if size == 0:
            stream.readline()  # trailing CRLF
            break
        chunks.append(stream.read(size))
        stream.readline()  # CRLF after chunk
    return b"".join(chunks)


# Shared global daemon state in tunnel.json (one per machine); cross-branch caveat in AGENTS.md.


def _state_path() -> Path:
    return (
        PlatformDirs("trapi-testing-tools", "biothings").user_state_path / "tunnel.json"
    )


def _daemon_log_path() -> Path:
    return (
        PlatformDirs("trapi-testing-tools", "biothings").user_state_path
        / "tunnel-daemon.log"
    )


def read_tunnel_info() -> dict[str, Any] | None:
    """Load the shared daemon's persisted tunnel info, or ``None`` if missing/invalid."""
    try:
        data = json.loads(_state_path().read_text(encoding="utf8"))
    except (OSError, json.JSONDecodeError):
        return None
    if (
        not isinstance(data, dict)
        or not {
            "pid",
            "receiver_url",
            "tunnel_url",
        }
        <= data.keys()
    ):
        return None
    return data


def write_tunnel_info(*, pid: int, receiver_url: str, tunnel_url: str) -> None:
    """Atomically persist the running daemon's tunnel info."""
    path = _state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(
        json.dumps(
            {
                "pid": pid,
                "receiver_url": receiver_url,
                "tunnel_url": tunnel_url,
                "created": time.time(),
            }
        ),
        encoding="utf8",
    )
    tmp.replace(path)


def clear_tunnel_info() -> None:
    """Remove the shared tunnel state file (best effort)."""
    _state_path().unlink(missing_ok=True)


def daemon_alive(info: dict[str, Any]) -> bool:
    """Whether the daemon pid in ``info`` is still running."""
    try:
        os.kill(int(info["pid"]), 0)
    except ProcessLookupError:
        return False
    except OSError:
        return True  # exists but not signalable by us
    return True


class CallbackReceiver:
    """Threaded HTTP server for callback bodies.

    Services POST results to `/callback/{token}`; a body is then claimed once, either
    in-process via `wait` (direct mode) or over HTTP via `GET /result/{token}` (the
    daemon hands callbacks back to a separate `tt test` process this way).
    """

    def __init__(self, bind: str, port: int, verbose: bool = False) -> None:
        """Start the server on ``bind:port`` (port 0 picks an ephemeral port).

        ``verbose`` logs each received callback / unexpected request to stderr (used by
        the daemon, whose stderr is captured to ``tunnel-daemon.log`` for diagnosis).
        """
        self._payloads: dict[str, tuple[bytes, float]] = {}
        self._events: dict[str, threading.Event] = {}
        self._lock = threading.Lock()
        self._last_activity = time.monotonic()
        self._verbose = verbose

        self._server = ThreadingHTTPServer((bind, port), self._make_handler())
        self.port = self._server.server_address[1]

        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    def _log(self, message: str) -> None:
        if self._verbose:
            print(f"[receiver] {message}", file=sys.stderr, flush=True)

    def register(self) -> str:
        """Reserve a token so its callback can be awaited in-process via `wait`."""
        token = uuid4().hex
        with self._lock:
            self._events[token] = threading.Event()
        return token

    def wait(self, token: str, timeout: float) -> bytes | None:
        """Block until the token's callback arrives (or timeout); return its body."""
        event = self._events.get(token)
        if event is None or not event.wait(timeout):
            return None
        with self._lock:
            item = self._payloads.pop(token, None)
            self._events.pop(token, None)
        return item[0] if item is not None else None

    def idle_seconds(self) -> float:
        """Seconds since the last callback POST or result claim."""
        return time.monotonic() - self._last_activity

    def sweep(self, ttl: float) -> None:
        """Drop received bodies that were never claimed within ``ttl`` seconds."""
        now = time.monotonic()
        with self._lock:
            stale = [t for t, (_b, ts) in self._payloads.items() if now - ts > ttl]
            for token in stale:
                self._payloads.pop(token, None)

    def close(self) -> None:
        """Stop the server and release its socket."""
        self._server.shutdown()
        self._server.server_close()

    def _store(self, token: str, body: bytes) -> None:
        with self._lock:
            self._payloads[token] = (body, time.monotonic())
            self._last_activity = time.monotonic()
            event = self._events.get(token)
        if event is not None:
            event.set()

    def _take(self, token: str) -> bytes | None:
        with self._lock:
            self._last_activity = time.monotonic()
            item = self._payloads.pop(token, None)
        return item[0] if item is not None else None

    def _make_handler(self) -> type[BaseHTTPRequestHandler]:
        receiver = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:  # noqa: N802 (BaseHTTPRequestHandler API)
                route, token = _split_route(self.path)
                body = self._read_body()
                if route == "callback" and token:
                    receiver._store(token, body)
                    receiver._log(f"callback received: token={token[:8]}… {len(body)}B")
                    self.send_response(200)
                else:
                    receiver._log(f"unexpected {self.command} {self.path}")
                    self.send_response(404)
                self.end_headers()

            def do_GET(self) -> None:  # noqa: N802 (BaseHTTPRequestHandler API)
                route, token = _split_route(self.path)
                if route != "result" or not token:
                    receiver._log(f"unexpected {self.command} {self.path}")
                    self.send_response(404)
                    self.end_headers()
                    return
                body = receiver._take(token)
                if body is None:
                    self.send_response(204)  # not arrived yet (client polls); no log
                    self.end_headers()
                    return
                receiver._log(f"result claimed: token={token[:8]}… {len(body)}B")
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def _read_body(self) -> bytes:
                if self.headers.get("Transfer-Encoding", "").lower() == "chunked":
                    return _read_chunked(self.rfile)
                length = int(self.headers.get("Content-Length") or 0)
                return self.rfile.read(length) if length else b""

            def log_message(
                self, *args: object
            ) -> None:  # ty: ignore[invalid-method-override]
                pass  # silence default stderr access logging

        return Handler


class CloudflaredTunnel:
    """A cloudflared quick tunnel fronting a receiver (used inside the daemon).

    ``url`` is the assigned `*.trycloudflare.com` address (``None`` if it couldn't
    start); ``ready`` (advisory) records whether the edge link is up and the hostname
    resolves publicly (see `_edge_up`/`_dns_propagated`, and AGENTS.md for why).
    """

    # Exclude api.trycloudflare.com (cloudflared's request endpoint, seen in its logs).
    _URL_RE = re.compile(rb"https://(?!api\.)[-\w]+\.trycloudflare\.com")
    _METRICS_RE = re.compile(rb"metrics server on (127\.0\.0\.1:\d+)")
    _REGISTERED_RE = re.compile(rb"Registered tunnel connection")
    _DOH_RESOLVERS = ("https://1.1.1.1/dns-query", "https://8.8.8.8/dns-query")

    def __init__(
        self,
        port: int,
        cloudflared_path: str,
        startup_timeout: float = 30,
        ready_timeout: float = 20,
    ) -> None:
        """Spawn cloudflared, wait for a URL, then confirm readiness (see class doc)."""
        self.url: str | None = None
        self.ready = False
        self.reason = ""  # why url is None, for a clearer fallback message
        self._recent: deque[str] = deque(maxlen=25)
        self._metrics_addr: str | None = None
        self._registered = threading.Event()
        self._url_ready = threading.Event()
        self._proc: subprocess.Popen[bytes] | None = None

        if shutil.which(cloudflared_path) is None:
            self.reason = "not installed"
            return

        self._proc = subprocess.Popen(
            [
                cloudflared_path,
                "tunnel",
                "--no-autoupdate",
                "--url",
                f"http://127.0.0.1:{port}",
                "--metrics",
                "127.0.0.1:0",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
        threading.Thread(target=self._drain_stderr, daemon=True).start()

        # Fail fast if cloudflared exits before a URL (rate-limited / TLS-intercepted).
        deadline = time.monotonic() + startup_timeout
        while time.monotonic() < deadline:
            if self._url_ready.wait(0.25):
                break
            if self._proc.poll() is not None:
                break

        if self.url is None:
            self.reason = "cloudflared did not report a tunnel URL (see output below)"
            return

        self.ready = self._await_ready(ready_timeout)

    def recent_output(self) -> str:
        """Recent cloudflared stderr lines, for diagnosing a failed start."""
        return "\n".join(self._recent)

    def close(self) -> None:
        """Terminate the cloudflared subprocess."""
        if self._proc is None:
            return
        self._proc.terminate()
        try:
            self._proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self._proc.kill()

    def _await_ready(self, timeout: float) -> bool:
        """Wait until the edge link is up and the hostname resolves via public DNS."""
        host = urlparse(self.url or "").hostname or ""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self._edge_up() and self._dns_propagated(host):
                return True
            time.sleep(0.5)
        return False

    def _dns_propagated(self, host: str) -> bool:
        """Whether public DoH resolvers resolve ``host`` (proxy for the remote service).

        Uses DoH rather than the local resolver, requiring every reachable resolver to
        return an answer (all-unreachable → not confirmed).
        """
        reached_any = False
        for resolver in self._DOH_RESOLVERS:
            try:
                data = httpx.get(
                    resolver,
                    params={"name": host, "type": "A"},
                    headers={"accept": "application/dns-json"},
                    timeout=2,
                ).json()
            except (httpx.HTTPError, ValueError):
                continue
            reached_any = True
            if data.get("Status") != 0 or not data.get("Answer"):
                return False
        return reached_any

    def _edge_up(self) -> bool:
        """Whether cloudflared has registered an edge connection.

        Confirmed via the registration log line or the `/ready` metrics endpoint (both
        local; DNS is checked separately by `_dns_propagated`).
        """
        if self._registered.is_set():
            return True
        if self._metrics_addr is None:
            return False
        try:
            response = httpx.get(f"http://{self._metrics_addr}/ready", timeout=2)
            return int(response.json().get("readyConnections", 0)) >= 1
        except (httpx.HTTPError, ValueError, TypeError):
            return False

    def _drain_stderr(self) -> None:
        """Scan stderr for the URL, metrics address, and edge registration."""
        assert self._proc is not None and self._proc.stderr is not None
        for line in self._proc.stderr:
            self._recent.append(line.decode(errors="replace").rstrip())
            if self.url is None and (match := self._URL_RE.search(line)):
                self.url = match.group(0).decode()
                self._url_ready.set()
            if self._metrics_addr is None and (
                metrics := self._METRICS_RE.search(line)
            ):
                self._metrics_addr = metrics.group(1).decode()
            if not self._registered.is_set() and self._REGISTERED_RE.search(line):
                self._registered.set()


def _await_via_daemon(
    daemon: dict[str, Any], token: str, timeout: float
) -> bytes | None:
    """Poll the daemon's local `/result/{token}` until the callback arrives.

    Bails out early (rather than hanging) if the daemon process has died — otherwise a
    crashed daemon would leave the poll silently retrying a dead endpoint forever.
    """
    result_url = f"{daemon['receiver_url']}/result/{token}"
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            response = httpx.get(result_url, timeout=10)
            if response.status_code == httpx.codes.OK:
                return response.content
        except httpx.HTTPError:
            if not daemon_alive(daemon):
                console.print(
                    "[yellow]callback daemon is no longer running; stopping wait.[/]"
                )
                return None
        time.sleep(1)
    return None


def start_tunnel() -> tuple[dict[str, Any] | None, str]:
    """Ensure the shared tunnel daemon is running, reusing or spawning as needed.

    Returns ``(info, "")`` when running, else ``(None, reason)`` (callers phrase the
    fallback); reuse is gated on the daemon's own loopback address, not the tunnel.
    """
    cfg = CONFIG.callback

    info = read_tunnel_info()
    if (
        info is not None
        and daemon_alive(info)
        and url_reachable(info["receiver_url"], 2)
    ):
        return info, ""

    if (
        not os.environ.get("TTT_TUNNEL_URL")
        and shutil.which(cfg.cloudflared_path) is None
    ):
        return None, "cloudflared not installed (e.g. `brew install cloudflared`)"

    log_path = _daemon_log_path()
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with console.status(
        "Starting cloudflared tunnel (shared, persists in background)..."
    ):
        with log_path.open("w", encoding="utf8") as logfile:
            proc = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "trapi_testing_tools.callback_daemon",
                    "--bind",
                    cfg.bind,
                    "--port",
                    str(cfg.port),
                    "--cloudflared-path",
                    cfg.cloudflared_path,
                ],
                stdout=logfile,
                stderr=logfile,
                start_new_session=True,
            )
        deadline = time.monotonic() + _DAEMON_STARTUP_TIMEOUT
        while time.monotonic() < deadline:
            info = read_tunnel_info()
            if info is not None and daemon_alive(info):
                return info, ""
            if proc.poll() is not None:
                break  # daemon exited before becoming ready
            time.sleep(0.5)

    return None, f"cloudflared tunnel unavailable (see {log_path})"


class CallbackSession:
    """Resolves callback reachability for one `tt test` run.

    Direct mode uses a per-run local receiver (closed at run end); tunnel mode uses the
    persistent global daemon (created lazily, never closed here).
    """

    def __init__(self, mode: str, host: str, bind: str, port: int) -> None:
        """Configure the session; infrastructure is created lazily, not here."""
        self.mode = mode
        self.host = host
        self.bind = bind
        self.port = port

        self._receiver: CallbackReceiver | None = None
        self._daemon: dict[str, Any] | None = None
        self._daemon_failed = False
        self._token_backend: dict[str, str] = {}

    def prepare(self, url: str) -> ResolvedMode:
        """Resolve the effective mode for a target, starting any infra it needs."""
        mode = self.mode
        if mode == "auto":
            mode = "direct" if _is_local_target(url) else "tunnel"

        if mode == "direct":
            self._ensure_receiver()
            return "direct"
        if mode == "tunnel":
            return "tunnel" if self._ensure_daemon() else "poll"
        return "poll"

    def callback_for(self, mode: ResolvedMode) -> tuple[str, str]:
        """Mint a token and return ``(token, callback_url)`` for the given mode."""
        if mode == "tunnel":
            assert self._daemon is not None  # prepare() connected it before tunnel mode
            token = uuid4().hex
            self._token_backend[token] = "tunnel"
            return token, f"{self._daemon['tunnel_url']}/callback/{token}"

        receiver = self._ensure_receiver()
        token = receiver.register()
        self._token_backend[token] = "direct"
        return token, f"http://{self.host}:{receiver.port}/callback/{token}"

    def wait(self, token: str, timeout: float) -> bytes | None:
        """Block for the token's callback body (or ``None`` on timeout)."""
        if self._token_backend.get(token) == "tunnel":
            assert self._daemon is not None
            return _await_via_daemon(self._daemon, token, timeout)
        if self._receiver is None:
            return None
        return self._receiver.wait(token, timeout)

    def close(self) -> None:
        """Tear down the per-run receiver (the session daemon persists across runs)."""
        if self._receiver is not None:
            self._receiver.close()

    def _ensure_receiver(self) -> CallbackReceiver:
        if self._receiver is None:
            self._receiver = CallbackReceiver(self.bind, self.port)
        return self._receiver

    def _ensure_daemon(self) -> dict[str, Any] | None:
        if self._daemon is None and not self._daemon_failed:
            info, reason = start_tunnel()
            if info is None:
                console.print(
                    f"[yellow]{reason}; falling back to polling for async queries.[/]"
                )
            self._daemon = info
            self._daemon_failed = info is None
        return self._daemon


@contextmanager
def callback_session(mode: str | None = None) -> Iterator[CallbackSession]:
    """Session context manager for a run, honoring an optional mode override."""
    cfg = CONFIG.callback
    session = CallbackSession(
        mode=mode or cfg.mode,
        host=cfg.host,
        bind=cfg.bind,
        port=cfg.port,
    )
    try:
        yield session
    finally:
        session.close()
