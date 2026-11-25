"""Append one JSONL record per external model call."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "runs.jsonl"
REQUIRED = {"model", "parameters", "seed", "latency_seconds", "cost"}


def log_model_call(record: dict[str, Any], path: Path = RUNS) -> None:
    missing = REQUIRED - record.keys()
    if missing:
        raise ValueError(f"Model-call record missing fields: {', '.join(sorted(missing))}")
    payload = {"timestamp_utc": datetime.now(timezone.utc).isoformat(), **record}
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(payload, ensure_ascii=False) + "\n")
