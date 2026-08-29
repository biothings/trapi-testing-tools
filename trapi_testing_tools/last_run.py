"""Persistence of the most recent ``tt test`` invocation, for ``--repeat``.

The effective (post-resolution) invocation is written to a small JSON file in the
platform state directory after every ``tt test`` run, so ``tt test -R`` can replay it —
including selections that were made interactively via the fuzzy prompts.

State is scoped per shell session so concurrent ``tt`` instances (multiple terminals,
tabs, tmux panes) don't clobber each other's ``-R``. See :func:`_session_key`.
"""

import json
import os
import re
import time
from pathlib import Path
from typing import Any

from platformdirs import PlatformDirs

_STATE_PREFIX = "last_test"
_STATE_SUFFIX = ".json"
_MAX_AGE_SECONDS = 30 * 24 * 3600  # prune abandoned per-session files after 30 days


def _session_key() -> str:
    """Best-effort identifier for the current shell session.

    Repeated ``tt`` invocations from the same terminal share this key, while separate
    terminals get distinct keys, so their ``-R`` state stays isolated. The POSIX session
    id (one per controlling terminal) is stable across intermediate wrappers (``uv run``)
    and pipelines. Honors a ``TTT_SESSION`` override, and falls back to the tty name and
    finally a shared ``default`` (the original single-file behavior) when no session
    identity is available.
    """
    override = os.environ.get("TTT_SESSION")
    if override:
        return override
    try:
        return f"sid{os.getsid(0)}"
    except (AttributeError, OSError):
        pass
    for fd in (2, 0, 1):  # stderr/stdin/stdout — whichever is still a tty
        try:
            return os.ttyname(fd)
        except OSError:
            continue
    return "default"


def _last_test_path() -> Path:
    """Path to this session's persisted last-test invocation file (platform state dir)."""
    # Same app identity as the test cache (utils.py), but user_state_path (durable, not a cache).
    state_dir = PlatformDirs("trapi-testing-tools", "biothings").user_state_path
    key = _session_key()
    if key == "default":
        return state_dir / f"{_STATE_PREFIX}{_STATE_SUFFIX}"
    safe = re.sub(r"[^A-Za-z0-9._-]", "-", key)[:64]
    return state_dir / f"{_STATE_PREFIX}_{safe}{_STATE_SUFFIX}"


def _prune_stale(state_dir: Path) -> None:
    """Best-effort removal of per-session state files no longer being touched."""
    cutoff = time.time() - _MAX_AGE_SECONDS
    for path in state_dir.glob(f"{_STATE_PREFIX}_*{_STATE_SUFFIX}"):
        try:
            if path.stat().st_mtime < cutoff:
                path.unlink()
        except OSError:
            continue


def save_last_test(invocation: dict[str, Any]) -> None:
    """Persist the effective test invocation so ``tt test -R`` can replay it."""
    path = _last_test_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf8") as file:
        json.dump(invocation, file)

    _prune_stale(path.parent)


def load_last_test() -> dict[str, Any] | None:
    """Load this session's last persisted test invocation, or ``None`` if missing/unreadable."""
    try:
        with _last_test_path().open(encoding="utf8") as file:
            data = json.load(file)
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None
