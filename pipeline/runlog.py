"""One JSONL record per external model call, in ``runs.jsonl``.

Failed calls are logged too. A retry that finally succeeds still had three
calls, and the failures are evidence for ``FAILURES.md``.
"""
from __future__ import annotations

import json
import os
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from .config import PRIVATE_NAMES, RUNS, load_env

REQUIRED = {"model", "parameters", "seed", "latency_seconds", "cost"}


def log_model_call(record: dict[str, Any], path: Path = RUNS) -> None:
    missing = REQUIRED - record.keys()
    if missing:
        raise ValueError(f"Model-call record missing fields: {', '.join(sorted(missing))}")
    payload = {"timestamp_utc": datetime.now(timezone.utc).isoformat(), **record}
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(payload, ensure_ascii=False) + "\n")


def _redact(text: str) -> str:
    """Mask a private value if one leaked into an error message."""
    load_env()
    for name in PRIVATE_NAMES:
        value = os.environ.get(name, "")
        if len(value) >= 8:
            text = text.replace(value, "***")
    return text


@contextmanager
def logged_call(
    *,
    stage: str,
    target: str,
    model: str,
    parameters: dict[str, Any],
    seed: int | None,
    attempt: int = 1,
    path: Path = RUNS,
) -> Iterator[dict[str, Any]]:
    """Time one model call and append a line for it, whether it succeeds or fails.

    The call is the body of the ``with`` block. Before leaving it, the caller
    fills in what came back: ``output``, ``output_sha256``, ``cost`` and so on.
    """
    record: dict[str, Any] = {
        "stage": stage,
        "target": target,
        "model": model,
        "parameters": parameters,
        "seed": seed,
        "attempt": attempt,
        "status": "ok",
        "error": None,
        "cost": 0.0,
        "cost_basis": "free tier",
    }
    started = time.perf_counter()
    try:
        yield record
    except Exception as exc:
        record["status"] = "error"
        record["error"] = _redact(f"{type(exc).__name__}: {exc}")[:600]
        raise
    finally:
        record["latency_seconds"] = round(time.perf_counter() - started, 3)
        log_model_call(record, path)
