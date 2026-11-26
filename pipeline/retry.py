"""Retry a model call that failed for a reason that may go away."""
from __future__ import annotations

import json
import random
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, TypeVar

from .config import OUTPUTS

T = TypeVar("T")


class TransientError(RuntimeError):
    """A failure worth retrying: a rate limit, a server error, a dropped connection."""

    def __init__(self, message: str, retry_after: float | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


def _wait_file(service: str | None) -> Path | None:
    return OUTPUTS / "_build" / f"wait-{service}.json" if service else None


def _asked_to_wait(service: str | None) -> tuple[str, datetime] | None:
    """The wait a service asked for, if it is still going on."""
    path = _wait_file(service)
    if path is None or not path.exists():
        return None
    try:
        saved = json.loads(path.read_text(encoding="utf-8"))
        until = datetime.fromisoformat(saved["until"])
    except (OSError, ValueError, KeyError, TypeError):
        return None
    return (saved.get("reason", "a failed call"), until) if until > datetime.now(timezone.utc) else None


def with_retries(
    action: Callable[[int], T],
    *,
    attempts: int = 4,
    base_delay: float = 2.0,
    max_delay: float = 60.0,
    max_server_wait: float = 120.0,
    service: str | None = None,
    sleep: Callable[[float], None] = time.sleep,
    notify: Callable[[str], None] = print,
) -> T:
    """Run ``action(attempt)`` and, on a TransientError, wait and try again.

    The wait doubles each time (2 s, 4 s, 8 s, ...) with a little jitter, so
    that clients which failed together do not retry together. A waiting time
    asked for by the server wins, up to ``max_server_wait``. A server that asks
    for longer than that is not answered by sitting still: the run stops with a
    clear message instead, and what is already made stays made.

    ``service`` is the name of the service called. When it asks for a long
    wait, that is remembered until the wait is over, so that no more calls are
    sent to be refused meanwhile.
    """
    if service:
        waiting = _asked_to_wait(service)
        if waiting:
            until = waiting[1].astimezone()
            raise TransientError(
                f"{waiting[0]}, and that service asked to be left until {until:%H:%M}. "
                "Everything made so far is kept: run the command again after that time."
            )
    for attempt in range(1, attempts + 1):
        try:
            return action(attempt)
        except TransientError as exc:
            if attempt == attempts:
                raise
            if exc.retry_after is not None:
                if exc.retry_after > max_server_wait:
                    path = _wait_file(service)
                    until = datetime.now(timezone.utc) + timedelta(seconds=exc.retry_after)
                    if path is not None:
                        path.parent.mkdir(parents=True, exist_ok=True)
                        path.write_text(
                            json.dumps({"reason": str(exc), "until": until.isoformat(), "seconds": exc.retry_after}),
                            encoding="utf-8",
                        )
                    raise TransientError(
                        f"{exc}, which asks for a wait of {exc.retry_after:.0f}s, until about "
                        f"{until.astimezone():%H:%M} local time. That is too long to sit out. "
                        "Everything made so far is kept: run the command again later and it carries on from there."
                    ) from exc
                delay = exc.retry_after
            else:
                delay = min(max_delay, base_delay * 2 ** (attempt - 1)) * random.uniform(0.8, 1.2)
            notify(f"    attempt {attempt} failed: {exc}. Retrying in {delay:.1f}s")
            sleep(max(0.0, delay))
    raise AssertionError("unreachable: the loop returns or raises")
