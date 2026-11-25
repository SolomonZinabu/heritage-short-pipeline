"""The Heritage Short pipeline.

One file, ``storyboard.json`` at the repository root, is the contract between
the stages. Each stage reads it, writes its outputs under ``outputs/``, and
records every model call in ``runs.jsonl``.

Run everything with ``python -m pipeline film``, or one stage at a time with
``python -m pipeline <stage>``.
"""
