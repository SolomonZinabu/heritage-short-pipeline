"""Thin clients for the hosted models.

Each client makes one kind of call. It turns network trouble and busy servers
into a TransientError, which the stages retry, and leaves every other failure
to be reported as it is.
"""
from __future__ import annotations

import requests

from ..retry import TransientError

# Status codes that usually clear up on their own.
TRANSIENT_STATUSES = {408, 409, 429, 500, 502, 503, 504}


class ProviderError(RuntimeError):
    """The service answered, but not with what was asked for."""


def retry_after(response: requests.Response) -> float | None:
    """The waiting time a server asked for, in seconds, if it gave one."""
    value = response.headers.get("Retry-After")
    if value is None:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        return None


def post(url: str, *, timeout: float, **options) -> requests.Response:
    """One POST request.

    A dropped connection, a timeout or a busy server becomes a TransientError.
    Any other answer is returned for the caller to judge.
    """
    host = url.split("/")[2]
    try:
        response = requests.post(url, timeout=timeout, **options)
    except (requests.ConnectionError, requests.Timeout) as exc:
        raise TransientError(f"could not reach {host}: {type(exc).__name__}") from exc
    if response.status_code in TRANSIENT_STATUSES:
        raise TransientError(f"HTTP {response.status_code} from {host}", retry_after=retry_after(response))
    return response
