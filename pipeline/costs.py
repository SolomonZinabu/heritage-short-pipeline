"""Summarise ``runs.jsonl`` for ``COSTS.md``: the calls of each stage, how long they took, and what they would have cost.

The figures are read from the log, so they cannot drift from what was actually
called.
"""
from __future__ import annotations

import json
import statistics
from collections import defaultdict
from typing import Any

from .config import RUNS
from .util import say

COLUMNS = "| Stage | Model | Calls | Failed | Latency: median | mean | longest | List price | Made on |"
RULE = "|---|---|---:|---:|---:|---:|---:|---:|---|"


def load(path=RUNS) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def timed(call: dict[str, Any]) -> float | None:
    """How long one call took, or None when it was not timed. A call logged after the fact can have no figure."""
    value = call.get("latency_seconds")
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def table(records: list[dict[str, Any]]) -> str:
    """One row per stage and model, in the form COSTS.md uses."""
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        groups[(str(record.get("stage", "?")), str(record.get("model", "?")))].append(record)
    rows = [COLUMNS, RULE]
    for (stage, model), calls in sorted(groups.items()):
        measured = [timed(call) for call in calls]
        latencies = [value for value in measured if value is not None]
        untimed = len(calls) - len(latencies)
        prices = [float(call["list_price_usd"]) for call in calls if call.get("list_price_usd") is not None]
        places = sorted({str(call.get("place", "this machine")) for call in calls})

        def took(measure) -> str:
            return f"{measure(latencies):.1f} s" if latencies else "not known"

        if latencies and len(prices) == len(calls):
            price = f"${sum(prices):.4f}"
        elif prices:
            price = "known for some calls"
        else:
            price = "not known"
        note = f" ({untimed} not timed)" if untimed else ""
        rows.append(
            f"| {stage} | {model} | {len(calls)} | {sum(call.get('status') == 'error' for call in calls)} "
            f"| {took(statistics.median)} | {took(statistics.mean)} | {took(max)}{note} | {price} | {', '.join(places)} |"
        )
    return "\n".join(rows)


def gpu_minutes(records: list[dict[str, Any]]) -> float:
    """The GPU time spent on calls that ran on Kaggle. Downloading and installing are not counted."""
    busy = [timed(call) for call in records if call.get("place") == "kaggle"]
    return sum(value for value in busy if value is not None) / 60


def report(path=RUNS) -> str:
    records = load(path)
    if not records:
        return "runs.jsonl is empty: no model has been called yet."
    text = table(records)
    kaggle = [call for call in records if call.get("place") == "kaggle"]
    if kaggle:
        text += f"\n\nGPU time on the {len(kaggle)} call(s) made on Kaggle: {gpu_minutes(records):.1f} minutes, not counting download and installation."
    return text


def main() -> int:
    say(report())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
