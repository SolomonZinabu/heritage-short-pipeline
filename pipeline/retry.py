"""Retry a model call that failed for a reason that may go away."""
from __future__ import annotations

import random
import time
from typing import Callable, TypeVar

T = TypeVar("T")


class TransientError(RuntimeError):
    """A failure worth retrying: a rate limit, a server error, a dropped connection."""

    def __init__(self, message: str, retry_after: float | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


def with_retries(
    action: Callable[[int], T],
    *,
    attempts: int = 4,
    base_delay: float = 2.0,
    max_delay: float = 60.0,
    sleep: Callable[[float], None] = time.sleep,
    notify: Callable[[str], None] = print,
) -> T:
    """Run ``action(attempt)`` and, on a TransientError, wait and try again.

    The wait doubles each time (2 s, 4 s, 8 s, ...) with a little jitter, so
    that clients which failed together do not retry together. A waiting time
    asked for by the server always wins.
    """
    for attempt in range(1, attempts + 1):
        try:
            return action(attempt)
        except TransientError as exc:
            if attempt == attempts:
                raise
            if exc.retry_after is not None:
                delay = exc.retry_after
            else:
                delay = min(max_delay, base_delay * 2 ** (attempt - 1)) * random.uniform(0.8, 1.2)
            notify(f"    attempt {attempt} failed: {exc}. Retrying in {delay:.1f}s")
            sleep(max(0.0, delay))
    raise AssertionError("unreachable: the loop returns or raises")
