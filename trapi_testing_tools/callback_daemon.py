"""Detached, global callback tunnel daemon.

Spawned by `callback.py` via `python -m trapi_testing_tools.callback_daemon`. Holds a
`CallbackReceiver` plus a cloudflared quick tunnel shared by all `tt test` runs on the
machine, so repeated runs reuse a single tunnel instead of creating one each time. It
persists in the background and self-terminates after an idle period (or on
`tt tunnel stop`), removing its state file so later runs know to start fresh.

Callbacks arrive at `POST /callback/{token}` (via the tunnel) and are handed to the
`tt test` process that owns the token via `GET /result/{token}` on the receiver's
local address.

Testing seam: set ``TTT_TUNNEL_URL`` to bypass cloudflared and advertise a given base
URL instead (``self`` = the receiver's own loopback URL).
"""

import argparse
import os
import signal
import sys
import threading
from types import FrameType

from trapi_testing_tools.callback import (
    CallbackReceiver,
    CloudflaredTunnel,
    clear_tunnel_info,
    url_reachable,
    write_tunnel_info,
)

_REACHABLE_TIMEOUT = 30


def _establish_tunnel(
    receiver: CallbackReceiver, cloudflared_path: str
) -> tuple[str | None, CloudflaredTunnel | None]:
    """Return ``(tunnel_url, tunnel)``; url is None if it couldn't be established."""
    override = os.environ.get("TTT_TUNNEL_URL")
    if override == "self":
        return f"http://127.0.0.1:{receiver.port}", None
    if override:
        return (override if url_reachable(override, _REACHABLE_TIMEOUT) else None), None

    tunnel = CloudflaredTunnel(receiver.port, cloudflared_path)
    return tunnel.url, tunnel


def _run(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="trapi_testing_tools.callback_daemon")
    parser.add_argument("--bind", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--cloudflared-path", default="cloudflared")
    parser.add_argument("--idle-timeout", type=float, default=1800)
    parser.add_argument("--reap-interval", type=float, default=5)
    parser.add_argument("--payload-ttl", type=float, default=900)
    args = parser.parse_args(argv)

    receiver = CallbackReceiver(args.bind, args.port, verbose=True)
    print(f"[daemon] pid {os.getpid()} receiver on port {receiver.port}", flush=True)
    tunnel_url, tunnel = _establish_tunnel(receiver, args.cloudflared_path)

    if tunnel_url is None:
        receiver.close()
        reason = tunnel.reason if tunnel is not None else "override URL unreachable"
        print(f"[daemon] tunnel unavailable: {reason}", flush=True)
        if tunnel is not None and tunnel.recent_output():
            print(
                f"[daemon] recent cloudflared output:\n{tunnel.recent_output()}",
                flush=True,
            )
            tunnel.close()
        return 1

    confirmed = tunnel.ready if tunnel is not None else True
    print(
        f"[daemon] tunnel ready: {tunnel_url} (readiness confirmed={confirmed})",
        flush=True,
    )
    write_tunnel_info(
        pid=os.getpid(),
        receiver_url=f"http://127.0.0.1:{receiver.port}",
        tunnel_url=tunnel_url,
    )

    stopping = threading.Event()

    def _stop(_signum: int, _frame: FrameType | None) -> None:
        stopping.set()

    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)

    try:
        while not stopping.is_set():
            stopping.wait(args.reap_interval)
            if stopping.is_set():
                break
            receiver.sweep(args.payload_ttl)
            if receiver.idle_seconds() > args.idle_timeout:
                break
    finally:
        clear_tunnel_info()
        receiver.close()
        if tunnel is not None:
            tunnel.close()
    return 0


if __name__ == "__main__":
    sys.exit(_run())
